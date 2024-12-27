#!/usr/bin/env python3
import datetime
import getpass
import json
import os.path
import pathlib
import shutil
import socket
import string
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from typing import Self


def error_and_exit(error_name: str, message: str):
    json.dump({"error_name": error_name, "message": message}, sys.stderr, indent="\t")
    exit(100)


base_dir = ""
image_name = ""
minisign_public_key_path = ""
try:
    target_path = sys.argv[1].strip()
    key_ref = sys.argv[2].strip()

    base_dir = os.path.dirname(target_path)
    image_name = os.path.basename(target_path)
    minisign_public_key_path = f"/opt/run-deploy/minisign/{key_ref}.pub"
except IndexError:
    error_and_exit(
        "ARGUMENT",
        "Must have two argument"
        )


def file_name_validation(value: str, name: str, flag: bool = False):
    extra = '.-_'
    if flag:
        extra = '-_'
    valid = not set(value).difference(string.ascii_letters + string.digits + extra)
    if not valid:
        error_and_exit(
            "FILE_NAME_VALIDATION",
            f"{name} must be `ascii letters + digits + {extra}`"
            )


file_name_validation(image_name, "image_name")

if not image_name.endswith(".squashfs"):
    error_and_exit(
        "FILE_NAME_VALIDATION",
        "Image name must end with '.squashfs'"
    )

os.chdir(base_dir)

try:
    subprocess.run(["minisign", "-Vqm", image_name, "-p", minisign_public_key_path], check=True)
    os.remove(f"{image_name}.minisig")
except subprocess.CalledProcessError:
    os.remove(image_name)
    os.remove(f"{image_name}.minisig")
    error_and_exit(
        "INVALID_SIGNATURE_AUTH",
        f"Invalid signature for '{image_name}'"
    )

mnt_point = f"/tmp/run-deploy-mount-{time.time()}"
os.mkdir(mnt_point, 0o700)

try:
    subprocess.run(["squashfuse", image_name, mnt_point], check=True)
except subprocess.CalledProcessError:
    os.remove(image_name)
    os.rmdir(mnt_point)
    error_and_exit(
        "MOUNT",
        f"Unable to mount '{image_name}'!"
    )

if not os.path.exists(f"{mnt_point}/_deploy/push.json"):
    subprocess.run(["umount", mnt_point])
    os.remove(image_name)
    os.rmdir(mnt_point)
    error_and_exit(
        "MANIFEST_NOT_EXIST",
        "'_deploy/push.json' does not exist"
    )

shutil.copytree(f"{mnt_point}/_deploy", image_name.removesuffix('.squashfs'))
subprocess.run(["umount", mnt_point])
if getpass.getuser() == "root":
    os.chown(image_name, 0, 0)
shutil.move(image_name, f"{image_name.removesuffix('.squashfs')}/{image_name}")

os.chdir(image_name.removesuffix('.squashfs'))

image_dir = ""
to_exec = ""
stamp = False
try:
    data = {}
    with open("push.json", "r", encoding='utf-8') as f:
        data = json.load(f)

    data = data[socket.gethostname()]
    image_dir = data['image-dir'].strip()
    to_exec = data['exec'].strip()
    stamp = data.get("stamp", False)
except (KeyError, json.JSONDecodeError):
    os.chdir('..')
    shutil.rmtree(f"{image_name.removesuffix('.squashfs')}")
    os.rmdir(mnt_point)
    error_and_exit(
        "MANIFEST_JSON",
        "Manifest is not well-formed!"
    )

# Sanity check
file_name_validation(to_exec, "to_exec")
file_name_validation(image_dir, "image_dir", True)

cleanup_dir = f"{image_name.removesuffix('.squashfs')}"


def clean_up():
    os.chdir('..')
    shutil.rmtree(cleanup_dir)
    os.rmdir(mnt_point)


@dataclass(frozen=True)
class Permission:
    full: bool
    admin: bool = False

    @classmethod
    def create(cls) -> Self:
        if not os.path.exists("/opt/run-deploy/permission"):
            return cls(admin=True, full=True)
        if not os.path.exists(f"/opt/run-deploy/permission/{key_ref}.toml"):
            return cls(full=False)
        permission = {}
        try:
            with open(f"/opt/run-deploy/permission/{key_ref}.toml", "rb") as f:
                permission = tomllib.load(f)
        except tomllib.TOMLDecodeError:
            return cls(full=False)
        if permission.get("admin", False):
            return cls(admin=True, full=True)
        if permission.get("banned", False):
            error_and_exit(
                "PERMISSION",
                "You are banned!"
            )
        if permission.get("full-access", False):
            return cls(full=True)

        image_permission = permission.get("metal", {})
        if image_permission.get("full-access", False):
            return cls(full=True)
        full = image_dir in image_permission.get("permit", [])

        return cls(full=full)

    def must_be_admin(self):
        if not self.admin:
            clean_up()
            error_and_exit(
                "PERMISSION",
                f"You must be admin for deploy. ( image: {image_dir} )"
            )

    def must_be_full(self):
        if self.admin:
            return
        if not self.full:
            clean_up()
            error_and_exit(
                "PERMISSION",
                f"You don't have full permission for deploy.( image: {image_dir} )"
            )


Permission.create().must_be_full()

os.makedirs(f"/opt/run-deploy/image/{image_dir}", exist_ok=True)

# Strict Mode
if os.path.exists("/opt/run-deploy/options/strict"):
    old_image_name = image_name
    now = datetime.datetime.now(datetime.UTC)
    if stamp:
        now = datetime.datetime.fromtimestamp(stamp, tz=datetime.UTC)
    image_name = f"{image_dir}-{now.year}-{now.month:02d}-{now.day:02d}_{now.hour:02d}-{now.minute:02d}-{now.second:02d}.squashfs"
    shutil.move(old_image_name, image_name)
    to_exec_path = pathlib.Path(to_exec)
    to_exec_path.write_text(f"""#!/bin/dash
cd /opt/run-deploy/image/{image_dir}
ln -sf {image_name} {image_dir}.squashfs || exit 1
/opt/run-deploy/script/deploy/{image_dir} || echo "/opt/run-deploy/script/deploy/{image_dir} not found or incorrect permission!" && exit 0
""", 'utf-8')
    to_exec_path.chmod(0o755)

if not os.path.exists(to_exec):
    clean_up()
    error_and_exit(
        "EXEC_NOT_EXIST",
        f"'{to_exec}' does not exist"
    )

# Move Image to location
shutil.move(image_name, f"/opt/run-deploy/image/{image_dir}/{image_name}")

# Copy Exec (Enforce name convention)
if getpass.getuser() == "root":
    os.chown(to_exec, 0, 0)
shutil.move(to_exec, f"/opt/run-deploy/image/{image_dir}/{image_name.removesuffix('.squashfs')}")

# Blame
pathlib.Path(f"/opt/run-deploy/image/{image_dir}/{image_name.removesuffix('.squashfs')}.blame").write_text(key_ref,
                                                                                                           'utf-8')
clean_up()

# Exec
try:
    subprocess.run([
        f"/opt/run-deploy/image/{image_dir}/{image_name.removesuffix('.squashfs')}"
    ], check=True)
except subprocess.CalledProcessError as e:
    error_and_exit(
        "EXEC_FAIL",
        f"Image script execution return error code {e.returncode}: {e.output.decode('utf-8')}"
    )
except PermissionError:
    error_and_exit(
        "EXEC_FAIL",
        f"Does not have permission to execute image script."
    )