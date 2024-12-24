#!/usr/bin/env python3
import argparse
import os.path
import pathlib
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from typing import Self

token_path = ""
minisign_public_key_path = ""
try:
    token_ref = os.environ['RUN_DEPLOY_TOKEN'].strip()
    key_ref = os.environ['RUN_DEPLOY_KEY'].strip()

    token_path = f"/tmp/run-deploy/run-deploy-token-{token_ref}"
    minisign_public_key_path = f"/opt/run-deploy/minisign/{key_ref}.pub"
except KeyError:
    print("Must have env `RUN_DEPLOY_TOKEN` and `RUN_DEPLOY_KEY`")
    exit(104)

try:
    subprocess.run(["minisign", "-Vqm", token_path, "-p", minisign_public_key_path], check=True)
    os.remove(token_path)
    os.remove(f"{token_path}.minisig")
except subprocess.CalledProcessError:
    print(f"Invalid signature for '{token_path}'", file=sys.stderr)
    os.remove(token_path)
    os.remove(f"{token_path}.minisig")
    exit(105)

parser = argparse.ArgumentParser(description='Queries and operate run-deploy system')

command_arg_list = ', '.join([
    'edition',
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'image-list'
])
parser.add_argument('command',
                    help=f"Commands: {command_arg_list}")
image_flag_list = ', '.join([
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert'
])
parser.add_argument('--image',
                    help=f"Required for: {image_flag_list}")
parser.add_argument('--revision', help="Required for: revert")

args = parser.parse_args()

image_ref = args.image
command_ref = args.command
revision_name = args.revision


def validate_input_image():
    if image_ref is None:
        print(f"'--image' is required for command: {command_ref}", file=sys.stderr)
        exit(102)
    if '/' in image_ref:
        print("'--image' must not have /", file=sys.stderr)
        exit(102)


def validate_input_revision():
    if revision_name is None:
        print(f"'--revision' is required for command: {command_ref}", file=sys.stderr)
        exit(102)
    if '/' in revision_name:
        print("'--revision' must not have /", file=sys.stderr)
        exit(102)


def get_image_path():
    return f"/opt/run-deploy/image/{image_ref}"


@dataclass(frozen=True)
class Permission:
    full: bool
    read: bool
    admin: bool = False

    @classmethod
    def create(cls) -> Self:
        if not os.path.exists("/opt/run-deploy/permission"):
            return cls(admin=True, full=True, read=True)
        if not os.path.exists(f"/opt/run-deploy/permission/{key_ref}.toml"):
            return cls(full=False, read=False)
        permission = {}
        with open(f"/opt/run-deploy/permission/{key_ref}.toml", "rb") as f:
            permission = tomllib.load(f)
        if permission.get("admin", False):
            return cls(admin=True, full=True, read=True)
        if permission.get("banned", False):
            print("You are banned!")
            exit(0)
        if permission.get("full-access", False):
            return cls(full=True, read=True)
        overall_read_access = permission.get("read-access", False)

        if image_ref is None:
            return cls(full=False, read=overall_read_access)

        image_permission = permission.get("metal", {})
        if image_permission.get("full-access", False):
            return cls(full=True, read=True)
        full = image_ref in image_permission.get("permit", [])
        read = overall_read_access or image_permission.get("read-access", False) or image_ref in image_permission.get(
            "permit-read", [])

        return cls(full=full, read=read)

    def must_be_admin(self):
        if not self.admin:
            print(f"You must be admin for command: {command_ref} ( image: {image_ref} )", file=sys.stderr)
            exit(101)

    def must_be_full(self):
        if self.admin:
            return
        if not self.full:
            print(
                f"You don't have full permission for command: {command_ref} ( image: {image_ref} )", file=sys.stderr)
            exit(101)

    def must_be_read(self):
        if self.admin or self.full:
            return
        if not self.read:
            print(
                f"You don't have read permission for command: {command_ref} ( image: {image_ref} )", file=sys.stderr)
            exit(101)


match command_ref:
    case "edition":
        print("remote-metal")
    case "last-deploy":
        validate_input_image()
        Permission.create().must_be_read()
        image_path = get_image_path()
        if os.path.exists(f"{image_path}/{image_ref}.squashfs"):
            print(os.path.basename(os.path.realpath(f"{image_path}/{image_ref}.squashfs")).removesuffix('.squashfs'))
        else:
            print("There isn't a last deploy", file=sys.stderr)
            exit(0)
    case "last-deploy-blame":
        validate_input_image()
        Permission.create().must_be_read()
        image_path = get_image_path()
        if os.path.exists(f"{image_path}/{image_ref}.squashfs"):
            last_path = os.path.realpath(f"{image_path}/{image_ref}.squashfs").removesuffix('.squashfs')
            print(pathlib.Path(f"{last_path}.blame").read_text('utf-8'))
        else:
            print("There isn't a last deploy", file=sys.stderr)
            exit(0)
    case "list-revision":
        validate_input_image()
        Permission.create().must_be_read()
        image_path = get_image_path()
        last_path = ""
        if os.path.exists(f"{image_path}/{image_ref}.squashfs"):
            last_path = os.path.basename(os.path.realpath(f"{image_path}/{image_ref}.squashfs")).removesuffix(
                '.squashfs')
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
        Permission.create().must_be_full()
        image_path = get_image_path()
        subprocess.run([
            f"{image_path}/{revision_name}"
        ], check=True)
    case "image-list":
        Permission.create().must_be_read()
        images = list(pathlib.Path("/opt/run-deploy/image").glob('*'))
        images.sort()
        for image in images:
            print(os.path.basename(image))
    case _:
        print(f"Command `{command_ref}` was not found!", file=sys.stderr)
        exit(103)
