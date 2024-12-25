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
    'exec',
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'list-incus',
    'list-image',
    'list-exec'
])
parser.add_argument('command', help=f"Commands: {command_arg_list}")
incus_flag_list = ', '.join([
    'exec',
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'list-image'
])
parser.add_argument('--incus', help=f"Required for: {incus_flag_list}")
image_flag_list = ', '.join([
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'list-exec'
])
parser.add_argument('--image', help=f"Required for: {image_flag_list}")
parser.add_argument('--revision', help="Required for: revert")
parser.add_argument('--cmd', help="Required for: exec")

args = parser.parse_args()

arg_incus = args.incus
arg_image = args.image
arg_command = args.command
arg_revision = args.revision
arg_cmd = args.cmd


def validate_input_image_incus():
    if arg_image is None or arg_incus is None:
        print(f"'--incus' and '--image' are required for command: {arg_command}", file=sys.stderr)
        exit(102)
    if '/' in arg_image or '/' in arg_incus:
        print("'--incus' and '--image' must not have /", file=sys.stderr)
        exit(102)


def validate_input_incus():
    if arg_incus is None:
        print(f"'--incus' is required for command: {arg_command}", file=sys.stderr)
        exit(102)
    if '/' in arg_incus:
        print("'--incus' must not have /", file=sys.stderr)
        exit(102)


def validate_input_exec():
    if arg_cmd is None:
        print(f"'--exec' is required for command: {arg_command}", file=sys.stderr)
        exit(102)
    if '/' in arg_cmd:
        print("'--exec' must not have /", file=sys.stderr)
        exit(102)


def validate_input_revision():
    if arg_revision is None:
        print(f"'--revision' is required for command: {arg_command}", file=sys.stderr)
        exit(102)
    if '/' in arg_revision:
        print("'--revision' must not have /", file=sys.stderr)
        exit(102)


def get_image_path():
    return f"/opt/run-deploy/image/{arg_image}"


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

        if arg_image is None or arg_incus is None:
            return cls(full=False, read=overall_read_access)

        incus_full_access = permission.get('incus-full-access', False)
        incus_read_access = permission.get('incus-read-access', False)

        image_permission = permission.get("incus", {}).get(arg_incus, {})
        if incus_full_access or image_permission.get("full-access", False):
            return cls(full=True, read=True)
        full = arg_image in image_permission.get("permit", [])
        read = incus_read_access or overall_read_access or image_permission.get("read-access",
                                                                                False) or arg_image in image_permission.get(
            "permit-read", [])

        return cls(full=full, read=read)

    def must_be_admin(self):
        if not self.admin:
            print(f"You must be admin for command: {arg_command} ( container: {arg_incus}, image: {arg_image} )",
                  file=sys.stderr)
            exit(101)

    def must_be_full(self):
        if self.admin:
            return
        if not self.full:
            print(
                f"You don't have full permission for command: {arg_command} ( container: {arg_incus}, image: {arg_image} )",
                file=sys.stderr)
            exit(101)

    def must_be_read(self):
        if self.admin or self.full:
            return
        if not self.read:
            print(
                f"You don't have read permission for command: {arg_command} ( container: {arg_incus}, image: {arg_image} )")
            exit(101)


match arg_command:
    case "edition":
        print("remote-incus")
    case "last-deploy":
        validate_input_image_incus()
        Permission.create().must_be_read()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", arg_incus, "--cwd", image_path, "--", "realpath", f"{arg_image}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        print(os.path.basename(last_path))
    case "last-deploy-blame":
        validate_input_image_incus()
        Permission.create().must_be_read()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", arg_incus, "--cwd", image_path, "--", "realpath", f"{arg_image}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        blame = subprocess.run([
            "incus", "exec", arg_incus, "--cwd", image_path, "--", "cat", f"{os.path.basename(last_path)}.blame"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip()
        print(blame)
    case "list-revision":
        validate_input_image_incus()
        Permission.create().must_be_read()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", arg_incus, "--cwd", image_path, "--", "realpath", f"{arg_image}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        last_path = os.path.basename(last_path)
        revision = subprocess.run([
            "incus", "exec", arg_incus, "--cwd", image_path, "--", "sh", "-c",
            "for f in *.blame; do (echo \"${f}:$(cat ${f})\";); done"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().splitlines()
        for index in range(len(revision)):
            revision_data = str(revision[index]).split(':')
            blame = revision_data.pop()
            arg_revision = ':'.join(revision_data).removesuffix('.blame')
            current = ""
            if arg_revision == last_path:
                current = "     *CURRENT*"
            revision[index] = f"{arg_revision}   blame: {blame}{current}"
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
            "incus", "exec", arg_incus, "--", f"{image_path}/{arg_revision}"
        ], check=True)
    case "list-incus":
        Permission.create().must_be_read()
        subprocess.run([
            "incus", "list", "-c", "n", "-f", "csv"
        ])
    case "list-image":
        validate_input_incus()
        Permission.create().must_be_read()
        try:
            images = subprocess.run([
                "incus", "exec", arg_incus, "--cwd", "/opt/run-deploy/image", "--", "ls", "-1A"
            ], check=True, capture_output=True).stdout.decode('utf-8').strip().splitlines()
            images.sort()
            for image in images:
                print(image)
        except subprocess.CalledProcessError:
            print("")
    case "exec":
        validate_input_incus()
        validate_input_exec()
        Permission.create().must_be_admin()
        try:
            subprocess.run([
                "incus", "exec", arg_incus, "--", f"/opt/run-deploy/exec/{arg_cmd}"
            ], check=True)
        except subprocess.CalledProcessError as e:
            exit(e.returncode)
    case "list-exec":
        validate_input_incus()
        Permission.create().must_be_admin()
        try:
            exec_list = subprocess.run([
                "incus", "exec", arg_incus, "--cwd", "/opt/run-deploy/exec", "--", "ls", "-1A"
            ], check=True, capture_output=True).stdout.decode('utf-8').strip().splitlines()
            exec_list.sort()
            for ex in exec_list:
                print(ex)
        except subprocess.CalledProcessError:
            print("")
            exit(0)
    case _:
        print(f"Command `{arg_command}` was not found!", file=sys.stderr)
        exit(103)
