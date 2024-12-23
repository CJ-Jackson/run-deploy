#!/usr/bin/env python3
import argparse
import os.path
import subprocess
import sys

token_path = ""
minisign_public_key_path = ""
try:
    token_ref = os.environ['RUN_DEPLOY_TOKEN'].strip()
    key_ref = os.environ['RUN_DEPLOY_KEY'].strip()

    token_path = f"/tmp/run-deploy/run-deploy-token-{token_ref}"
    minisign_public_key_path = f"/opt/run-deploy/minisign/{key_ref}.pub"
except KeyError:
    print("Must have env `RUN_DEPLOY_TOKEN` and `RUN_DEPLOY_KEY`")
    exit(3)

try:
    subprocess.run(["minisign", "-Vqm", token_path, "-p", minisign_public_key_path], check=True)
    os.remove(token_path)
    os.remove(f"{token_path}.minisig")
except subprocess.CalledProcessError:
    print(f"Invalid signature for '{token_path}'", file=sys.stderr)
    os.remove(token_path)
    os.remove(f"{token_path}.minisig")
    exit(5)

parser = argparse.ArgumentParser(description='Queries and operate run-deploy system')

parser.add_argument('command', help="Possible commands: edition, last-deploy, last-deploy-blame, list-revision and revert")
parser.add_argument('--incus')
parser.add_argument('--image')
parser.add_argument('--revision')

args = parser.parse_args()

incus_name = args.incus
image_ref = args.image
command_ref = args.command
revision_name = args.revision

def validate_input_image_incus():
    if image_ref is None or incus_name is None:
        print(f"'--incus' and '--image' are required for command: {command_ref}", file=sys.stderr)
        exit(1)
    if '/' in image_ref or '/' in incus_name:
        print("'--incus' and '--image' must not have /", file=sys.stderr)
        exit(1)

def validate_input_revision():
    if revision_name is None:
        print(f"'--revision' is required for command: {command_ref}", file=sys.stderr)
        exit(1)
    if '/' in revision_name:
        print("'--revision' must not have /", file=sys.stderr)
        exit(1)

def get_image_path():
    return f"/opt/run-deploy/image/{image_ref}"

match command_ref:
    case "edition":
        print("remote-incus")
    case "last-deploy":
        validate_input_image_incus()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "realpath", f"{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        print(os.path.basename(last_path))
    case "last-deploy-blame":
        validate_input_image_incus()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "realpath", f"{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        blame = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "cat", f"{os.path.basename(last_path)}.blame"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip()
        print(blame)
    case "list-revision":
        validate_input_image_incus()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "realpath", f"{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        last_path = os.path.basename(last_path)
        revision = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "sh", "-c", "for f in *.blame; do (echo \"${f}:$(cat ${f})\";); done"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().splitlines()
        for index in range(len(revision)):
            revision_data = str(revision[index]).split(':')
            blame = revision_data.pop()
            revision_name = ':'.join(revision_data).removesuffix('.blame')
            current = ""
            if revision_name == last_path:
                current = "     *CURRENT*"
            revision[index] = f"{revision_name}   blame: {blame}{current}"
        revision.sort()
        revision = list(reversed(revision))
        for rev in revision:
            print(rev)
    case "revert":
        validate_input_image_incus()
        validate_input_revision()
        image_path = get_image_path()
        subprocess.run([
            "incus", "exec", incus_name, "--", f"{image_path}/{revision_name}"
        ], check=True)
    case _:
        print(f"Command `{command_ref}` was not found!", file=sys.stderr)
        exit(1)