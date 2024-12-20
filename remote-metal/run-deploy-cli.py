#!/usr/bin/env python3
import os.path
import pathlib
import subprocess
import sys

token_path = ""
minisign_public_key_path = ""
try:
    token_ref = os.environ['RUN_DEPLOY_TOKEN'].strip()
    key_ref = os.environ['RUN_DEPLOY_KEY'].strip()

    token_path = f"/tmp/run-deploy-token-{token_ref}"
    minisign_public_key_path = f"/opt/local/minisign/{key_ref}.pub"
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

image_ref = ""
command_ref = ""
try:
    image_ref = sys.argv[1]
    command_ref = sys.argv[2]
except IndexError:
    print("Must have incus_name, image_ref and command_ref", file=sys.stderr)
    exit(1)

if '/' in image_ref:
    print("Image Ref must not have /", file=sys.stderr)

image_path = f"/opt/image/{image_ref}"

match command_ref:
    case "last-deploy":
        if os.path.exists(f"{image_path}/{image_ref}.squashfs"):
            print(os.path.basename(os.path.realpath(f"{image_path}/{image_ref}.squashfs")).removesuffix('.squashfs'))
        else:
            print("There isn't a last deploy", file=sys.stderr)
            exit(1)
    case "list-revision":
        revision = list(pathlib.Path(image_path).glob(f'*.squashfs'))
        for index in range(len(revision)):
            revision[index] = os.path.basename(revision[index]).removesuffix('.squashfs')
        revision.sort()
        try:
            revision = list(reversed(revision[1:]))
        except IndexError:
            exit()
        for rev in revision:
            print(rev)
    case "revert":
        revision_name = ""
        try:
            revision_name = sys.argv[3]
        except IndexError:
            print("Must have revision name", file=sys.stderr)
            exit(2)
        if '/' in revision_name:
            print("Revision name must not have /", file=sys.stderr)
            exit(2)
        subprocess.run([
            f"{image_path}/{revision_name}"
        ])