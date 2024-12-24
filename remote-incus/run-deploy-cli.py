#!/usr/bin/env python3
import argparse
import os.path
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
    'incus-list',
    'image-list'
])
parser.add_argument('command',
                    help=f"Commands: {command_arg_list}")

incus_flag_list = ', '.join([
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'image-list'
])
parser.add_argument('--incus',
                    help=f"Required for: {incus_flag_list}")
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

incus_name = args.incus
image_ref = args.image
command_ref = args.command
revision_name = args.revision


def validate_input_image_incus():
    if image_ref is None or incus_name is None:
        print(f"'--incus' and '--image' are required for command: {command_ref}", file=sys.stderr)
        exit(102)
    if '/' in image_ref or '/' in incus_name:
        print("'--incus' and '--image' must not have /", file=sys.stderr)
        exit(102)


def validate_input_incus():
    if incus_name is None:
        print(f"'--incus' is required for command: {command_ref}", file=sys.stderr)
        exit(102)
    if '/' in incus_name:
        print("'--incus' must not have /", file=sys.stderr)
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
            print("You are banned!", file=sys.stderr)
            exit(101)
        if permission.get("full-access", False):
            return cls(full=True, read=True)
        overall_read_access = permission.get("read-access", False)

        if image_ref is None or incus_name is None:
            return cls(full=False, read=overall_read_access)

        incus_full_access = permission.get('incus-full-access', False)
        incus_read_access = permission.get('incus-read-access', False)

        image_permission = permission.get("incus", {}).get(incus_name, {})
        if incus_full_access or image_permission.get("full-access", False):
            return cls(full=True, read=True)
        full = image_ref in image_permission.get("permit", [])
        read = incus_read_access or overall_read_access or image_permission.get("read-access",
                                                                                False) or image_ref in image_permission.get(
            "permit-read", [])

        return cls(full=full, read=read)

    def must_be_admin(self):
        if not self.admin:
            print(f"You must be admin for command: {command_ref} ( container: {incus_name}, image: {image_ref} )",
                  file=sys.stderr)
            exit(101)

    def must_be_full(self):
        if self.admin:
            return
        if not self.full:
            print(
                f"You don't have full permission for command: {command_ref} ( container: {incus_name}, image: {image_ref} )",
                file=sys.stderr)
            exit(101)

    def must_be_read(self):
        if self.admin or self.full:
            return
        if not self.read:
            print(
                f"You don't have read permission for command: {command_ref} ( container: {incus_name}, image: {image_ref} )")
            exit(101)


match command_ref:
    case "edition":
        print("remote-incus")
    case "last-deploy":
        validate_input_image_incus()
        Permission.create().must_be_read()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "realpath", f"{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        print(os.path.basename(last_path))
    case "last-deploy-blame":
        validate_input_image_incus()
        Permission.create().must_be_read()
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
        Permission.create().must_be_read()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "realpath", f"{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        last_path = os.path.basename(last_path)
        revision = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "sh", "-c",
            "for f in *.blame; do (echo \"${f}:$(cat ${f})\";); done"
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
        Permission.create().must_be_full()
        image_path = get_image_path()
        subprocess.run([
            "incus", "exec", incus_name, "--", f"{image_path}/{revision_name}"
        ], check=True)
    case "incus-list":
        Permission.create().must_be_read()
        subprocess.run([
            "incus", "list", "-c", "n", "-f", "csv"
        ])
    case "image-list":
        validate_input_incus()
        Permission.create().must_be_read()
        try:
            images = subprocess.run([
                "incus", "exec", incus_name, "--cwd", "/opt/run-deploy/image", "--", "ls", "-1A"
            ], check=True, capture_output=True).stdout.decode('utf-8').strip().splitlines()
            images.sort()
            for image in images:
                print(image)
        except subprocess.CalledProcessError:
            print("")
    case _:
        print(f"Command `{command_ref}` was not found!", file=sys.stderr)
        exit(103)
