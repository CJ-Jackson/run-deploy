#!/usr/bin/env python3
import argparse
import json
import os.path
import pathlib
import string
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from typing import Self


def error_and_exit(error_name: str, message: str):
    json.dump({"error_name": error_name, "message": message}, sys.stderr, indent="\t")
    exit(100)


token_path = ""
minisign_public_key_path = ""
try:
    token_ref = os.environ['RUN_DEPLOY_TOKEN'].strip()
    key_ref = os.environ['RUN_DEPLOY_KEY'].strip()

    token_path = f"/tmp/run-deploy/run-deploy-token-{token_ref}"
    minisign_public_key_path = f"/opt/run-deploy/minisign/{key_ref}.pub"
except KeyError:
    error_and_exit(
        "TOKEN_KEY",
        "Must have env `RUN_DEPLOY_TOKEN` and `RUN_DEPLOY_KEY`"
    )

try:
    subprocess.run(["minisign", "-Vqm", token_path, "-p", minisign_public_key_path], check=True)
    os.remove(token_path)
    os.remove(f"{token_path}.minisig")
except subprocess.CalledProcessError:
    os.remove(token_path)
    os.remove(f"{token_path}.minisig")
    error_and_exit(
    "INVALID_SIGNATURE_AUTH",
    f"Invalid signature for '{token_path}'"
    )

parser = argparse.ArgumentParser(description='Queries and operate run-deploy system')

command_arg_list = ', '.join([
    'edition',
    'exec',
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'list-image',
    'list-exec'
])
parser.add_argument('command', help=f"Commands: {command_arg_list}")
image_flag_list = ', '.join([
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert'
])
parser.add_argument('--image', help=f"Required for: {image_flag_list}")
parser.add_argument('--revision', help="Required for: revert")
parser.add_argument('--cmd', help="Required for: exec")

args = parser.parse_args()

arg_command = args.command
flag_image = args.image
flag_revision = args.revision
flag_cmd = args.cmd


def file_name_validation(value: str, name: str, flag: bool=False):
    extra = '.-_'
    if flag:
        extra = '-_'
    valid = not set(value).difference(string.ascii_letters + string.digits + extra)
    if not valid:
        error_and_exit(
            "FILE_NAME_VALIDATION",
            f"{name} must be `ascii letters + digits + {extra}`"
        )


def validate_input_image():
    if flag_image is None:
        error_and_exit(
            "FLAG_VALIDATION",
            f"'--image' is required for command: {arg_command}"
        )
    file_name_validation(flag_image, "flag_image", True)


def validate_input_revision():
    if flag_revision is None:
        error_and_exit(
            "FLAG_VALIDATION",
            f"'--revision' is required for command: {arg_command}"
        )
    file_name_validation(flag_revision, "flag_revision", True)


def validate_input_exec():
    if flag_cmd is None:
        error_and_exit(
            "FLAG_VALIDATION",
            f"'--exec' is required for command: {arg_command}"
        )
    file_name_validation(flag_cmd, "flag_cmd", True)


def get_image_path():
    return f"/opt/run-deploy/image/{flag_image}"


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
        try:
            with open(f"/opt/run-deploy/permission/{key_ref}.toml", "rb") as f:
                permission = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            return cls(full=False, read=False)
        if permission.get("admin", False):
            return cls(admin=True, full=True, read=True)
        if permission.get("banned", False):
            error_and_exit(
                "PERMISSION",
                "You are banned!"
            )
        if permission.get("full-access", False):
            return cls(full=True, read=True)
        overall_read_access = permission.get("read-access", False)

        if flag_image is None:
            return cls(full=False, read=overall_read_access)

        image_permission = permission.get("metal", {})
        if image_permission.get("full-access", False):
            return cls(full=True, read=True)
        full = flag_image in image_permission.get("permit", [])
        read = overall_read_access or image_permission.get("read-access", False) or flag_image in image_permission.get(
            "permit-read", [])

        return cls(full=full, read=read)

    def must_be_admin(self):
        if not self.admin:
            error_and_exit(
                "PERMISSION",
                f"You must be admin for command: {arg_command} ( image: {flag_image} )"
            )

    def must_be_full(self):
        if self.admin:
            return
        if not self.full:
            error_and_exit(
                "PERMISSION",
                f"You don't have full permission for command: {arg_command} ( image: {flag_image} )"
            )

    def must_be_read(self):
        if self.admin or self.full:
            return
        if not self.read:
            error_and_exit(
                "PERMISSION",
                f"You don't have read permission for command: {arg_command} ( image: {flag_image} )"
            )


match arg_command:
    case "edition":
        print("remote-metal")
    case "last-deploy":
        validate_input_image()
        Permission.create().must_be_read()
        image_path = get_image_path()
        if os.path.exists(f"{image_path}/{flag_image}.squashfs"):
            print(os.path.basename(os.path.realpath(f"{image_path}/{flag_image}.squashfs")).removesuffix('.squashfs'))
        else:
            print("There isn't a last deploy", file=sys.stderr)
            exit(0)
    case "last-deploy-blame":
        validate_input_image()
        Permission.create().must_be_read()
        image_path = get_image_path()
        if os.path.exists(f"{image_path}/{flag_image}.squashfs"):
            last_path = os.path.realpath(f"{image_path}/{flag_image}.squashfs").removesuffix('.squashfs')
            print(pathlib.Path(f"{last_path}.blame").read_text('utf-8'))
        else:
            print("There isn't a last deploy", file=sys.stderr)
            exit(0)
    case "list-revision":
        validate_input_image()
        Permission.create().must_be_read()
        image_path = get_image_path()
        last_path = ""
        if os.path.exists(f"{image_path}/{flag_image}.squashfs"):
            last_path = os.path.basename(os.path.realpath(f"{image_path}/{flag_image}.squashfs")).removesuffix(
                '.squashfs')
        else:
            print("There isn't a last deploy", file=sys.stderr)
            exit(0)
        revision = list(pathlib.Path(image_path).glob(f'*.blame'))
        for index in range(len(revision)):
            flag_revision = str(revision[index]).removesuffix('.blame')
            blame = pathlib.Path(f"{flag_revision}.blame").read_text('utf-8')
            flag_revision = os.path.basename(flag_revision)
            current = ""
            if flag_revision == last_path:
                current = "     *CURRENT*"
            revision[index] = f"{flag_revision}   blame: {blame}{current}"
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
            f"{image_path}/{flag_revision}"
        ], check=True)
    case "list-image":
        Permission.create().must_be_read()
        images = list(pathlib.Path("/opt/run-deploy/image").glob('*'))
        images.sort()
        for image in images:
            print(os.path.basename(image))
    case "exec":
        validate_input_exec()
        Permission.create().must_be_admin()
        try:
            subprocess.run([
                f"/opt/run-deploy/exec/{flag_cmd}"
            ], check=True)
        except FileNotFoundError:
            print("File Not Found", file=sys.stderr)
            exit(127)
        except PermissionError as e:
            print("Permission Error", file=sys.stderr)
            exit(13)
        except subprocess.CalledProcessError as e:
            exit(e.returncode)
    case "list-exec":
        Permission.create().must_be_admin()
        exec_list = pathlib.Path("/opt/run-deploy/exec").glob('*')
        for ex in exec_list:
            print(os.path.basename(ex))
    case _:
        error_and_exit(
            "COMMAND_NOT_FOUND",
            f"Command `{arg_command}` was not found!"
        )
