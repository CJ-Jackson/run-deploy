#!/usr/bin/env python3
import argparse
import os.path
import pathlib
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

parser.add_argument('command')
parser.add_argument('--image')
parser.add_argument('--revision')

args = parser.parse_args()

image_ref = args.image
command_ref = args.command
revision_name = args.revision

def validate_input_image():
    if image_ref is None:
        print(f"'--image' is required for command: {command_ref}", file=sys.stderr)
        exit(1)
    if '/' in image_ref:
        print("'--image' must not have /", file=sys.stderr)
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
    case "last-deploy":
        validate_input_image()
        image_path = get_image_path()
        if os.path.exists(f"{image_path}/{image_ref}.squashfs"):
            print(os.path.basename(os.path.realpath(f"{image_path}/{image_ref}.squashfs")).removesuffix('.squashfs'))
        else:
            print("There isn't a last deploy", file=sys.stderr)
            exit(0)
    case "last-deploy-blame":
        validate_input_image()
        image_path = get_image_path()
        if os.path.exists(f"{image_path}/{image_ref}.squashfs"):
            last_path = os.path.realpath(f"{image_path}/{image_ref}.squashfs").removesuffix('.squashfs')
            print(pathlib.Path(f"{last_path}.blame").read_text('utf-8'))
        else:
            print("There isn't a last deploy", file=sys.stderr)
            exit(0)
    case "list-revision":
        validate_input_image()
        image_path = get_image_path()
        last_path = ""
        if os.path.exists(f"{image_path}/{image_ref}.squashfs"):
            last_path = os.path.basename(os.path.realpath(f"{image_path}/{image_ref}.squashfs")).removesuffix('.squashfs')
        else:
            print("There isn't a last deploy", file=sys.stderr)
            exit(0)
        revision = list(pathlib.Path(image_path).glob(f'*.blame'))
        for index in range(len(revision)):
            revision_name = str(revision[index]).removesuffix('.blame')
            blame = pathlib.Path(f"{revision_name}.blame").read_text('utf-8')
            revision_name = os.path.basename(revision_name)
            current = ""
            if revision_name == last_path:
                current = "     *CURRENT*"
            revision[index] = f"{revision_name}   blame: {blame}{current}"
        revision.sort()
        revision = list(reversed(revision))
        for rev in revision:
            print(rev)
    case "revert":
        validate_input_image()
        validate_input_revision()
        image_path = get_image_path()
        subprocess.run([
            f"{image_path}/{revision_name}"
        ], check=True)
    case _:
        print(f"Command `{command_ref}` was not found!", file=sys.stderr)
        exit(1)