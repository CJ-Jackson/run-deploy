#!/usr/bin/env python3
import getpass
import json
import os.path
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from typing import Self

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
    print("Must have two argument", file=sys.stderr)
    exit(102)

if not image_name.endswith(".squashfs"):
    print("Image name must end with '.squashfs'", file=sys.stderr)
    exit(102)

os.chdir(base_dir)

try:
    subprocess.run(["minisign", "-Vqm", image_name, "-p", minisign_public_key_path], check=True)
    os.remove(f"{image_name}.minisig")
except subprocess.CalledProcessError:
    print(f"Invalid signature for '{image_name}'", file=sys.stderr)
    os.remove(image_name)
    os.remove(f"{image_name}.minisig")
    exit(107)

mnt_point = f"/tmp/run-deploy-mount-{time.time()}"
os.mkdir(mnt_point, 0o700)

try:
    subprocess.run(["squashfuse", image_name, mnt_point], check=True)
except subprocess.CalledProcessError:
    print(f"Unable to mount '{image_name}'!", file=sys.stderr)
    os.remove(image_name)
    os.rmdir(mnt_point)
    exit(106)

if not os.path.exists(f"{mnt_point}/_deploy/push.json"):
    subprocess.run(["umount", mnt_point])
    os.remove(image_name)
    os.rmdir(mnt_point)
    print("'_deploy/push' does not exist", file=sys.stderr)
    exit(106)

shutil.copytree(f"{mnt_point}/_deploy", image_name.removesuffix('.squashfs'))
subprocess.run(["umount", mnt_point])
if getpass.getuser() == "root":
    os.chown(image_name, 0, 0)
shutil.move(image_name, f"{image_name.removesuffix('.squashfs')}/{image_name}")

os.chdir(image_name.removesuffix('.squashfs'))

data = {}
with open("push.json", "r", encoding='utf-8') as f:
    data = json.load(f)

data = data[socket.gethostname()]

image_dir: str = data['image-dir'].strip()
to_exec: str = data['exec'].strip()

# Sanity check
valid = True
if '/' in to_exec or '/' in image_dir:
    valid = False

if not valid:
    print("Cannot have '/' in values, also image directory name must also be in file.", file=sys.stderr)
    exit(1002)


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
        with open(f"/opt/run-deploy/permission/{key_ref}.toml", "rb") as f:
            permission = tomllib.load(f)
        if permission.get("admin", False):
            return cls(admin=True, full=True)
        if permission.get("banned", False):
            print("You are banned!", file=sys.stderr)
            exit(101)
        if permission.get("full-access", False):
            return cls(full=True)

        image_permission = permission.get("metal", {})
        if image_permission.get("full-access", False):
            return cls(full=True)
        full = image_dir in image_permission.get("permit", [])

        return cls(full=full)

    def must_be_admin(self):
        if not self.admin:
            print(f"You must be admin for deploy. ( image: {image_dir} )", file=sys.stderr)
            exit(101)

    def must_be_full(self):
        if self.admin:
            return
        if not self.full:
            print(
                f"You don't have full permission for deploy.( image: {image_dir} )", file=sys.stderr)
            exit(101)


Permission.create().must_be_full()

os.makedirs(f"/opt/run-deploy/image/{image_dir}", exist_ok=True)

# Move Image to location
shutil.move(image_name, f"/opt/run-deploy/image/{image_dir}/{image_name}")

# Copy Exec (Enforce name convention)
if getpass.getuser() == "root":
    os.chown(to_exec, 0, 0)
shutil.move(to_exec, f"/opt/run-deploy/image/{image_dir}/{image_name.removesuffix('.squashfs')}")

# Blame
pathlib.Path(f"/opt/run-deploy/image/{image_dir}/{image_name.removesuffix('.squashfs')}.blame").write_text(key_ref,
                                                                                                           'utf-8')

# Clean up
os.chdir('..')
shutil.rmtree(f"{image_name.removesuffix('.squashfs')}")
os.rmdir(mnt_point)

# Exec
subprocess.run([
    f"/opt/run-deploy/image/{image_dir}/{image_name.removesuffix('.squashfs')}"
], check=True)
