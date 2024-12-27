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

base_dir = ""
image_name = ""
try:
    target_path = sys.argv[1].strip()

    base_dir = os.path.dirname(target_path)
    image_name = os.path.basename(target_path)
except IndexError:
    print("Must have one argument", file=sys.stderr)
    exit(1)


def file_name_validation(value: str, name: str, flag: bool=False):
    extra = '.-_'
    if flag:
        extra = '-_'
    valid = not set(value).difference(string.ascii_letters + string.digits + extra)
    if not valid:
        print(f"{name} must be `ascii letters + digits + {extra}`")
        exit(102)


file_name_validation(image_name, "image_name")

if not image_name.endswith(".squashfs"):
    print("Image name must end with '.squashfs'", file=sys.stderr)
    exit(1)

os.chdir(base_dir)

mnt_point = f"/tmp/run-deploy-mount-{time.time()}"
os.mkdir(mnt_point, 0o700)

try:
    subprocess.run(["squashfuse", image_name, mnt_point], check=True)
except subprocess.CalledProcessError:
    print(f"Unable to mount '{image_name}'!", file=sys.stderr)
    os.remove(image_name)
    os.rmdir(mnt_point)
    exit(1)

if not os.path.exists(f"{mnt_point}/_deploy/push.json"):
    subprocess.run(["umount", mnt_point])
    os.remove(image_name)
    os.rmdir(mnt_point)
    print("'_deploy/push' does not exist", file=sys.stderr)
    exit(1)

shutil.copytree(f"{mnt_point}/_deploy", image_name.removesuffix('.squashfs'))
subprocess.run(["umount", mnt_point])
if getpass.getuser() == "root":
    os.chown(image_name, 0, 0)
os.rename(image_name, f"{image_name.removesuffix('.squashfs')}/{image_name}")

os.chdir(image_name.removesuffix('.squashfs'))

incus_name = ""
image_dir = ""
to_exec = ""
try:
    data = {}
    with open("push.json", "r", encoding='utf-8') as f:
        data = json.load(f)

    data = data[socket.gethostname()]
    incus_name = data['incus-name'].strip()
    image_dir = data['image-dir'].strip()
    to_exec = data['exec'].strip()
except (KeyError, json.JSONDecodeError):
    print("Manifest is not well-formed!", file=sys.stderr)
    os.chdir('..')
    shutil.rmtree(f"{image_name.removesuffix('.squashfs')}")
    os.rmdir(mnt_point)
    exit(108)

# Sanity check
file_name_validation(incus_name, "incus_name", True)
file_name_validation(to_exec, "to_exec")
file_name_validation(image_dir, "image_dir", True)

# Create directory if not exist
subprocess.run([
    "incus", "exec", incus_name, "--", "mkdir", "-p", f"/opt/run-deploy/image/{image_dir}"
], capture_output=True)

# Strict Mode
if os.path.exists("/opt/run-deploy/options/strict"):
    old_image_name = image_name
    now = datetime.datetime.now(datetime.UTC)
    image_name = f"{image_dir}-{now.year}-{now.month:02d}-{now.day:02d}_{now.hour:02d}-{now.minute:02d}-{now.second:02d}.squashfs"
    shutil.move(old_image_name, image_name)
    to_exec_path = pathlib.Path(to_exec)
    to_exec_path.write_text(f"""#!/bin/dash
cd /opt/run-deploy/image/{image_dir}
ln -s {image_name} {image_dir}.squashfs || exit 1
/opt/run-deploy/script/deploy/{image_dir} || echo "/opt/run-deploy/script/deploy/{image_dir} not found!" && exit 0
""", 'utf-8')
    to_exec_path.chmod(0o755)

# Upload Image to Incus container
subprocess.run([
    "incus", "file", "push", "--uid", "0", "--gid", "0", image_name, f"{incus_name}/opt/run-deploy/image/{image_dir}/"
], check=True)

# Copy Exec (Enforce name convention)
if to_exec != image_name.removesuffix('.squashfs'):
    shutil.copy(to_exec, image_name.removesuffix('.squashfs'))
    subprocess.run([
        "incus", "file", "push", "--uid", "0", "--gid", "0", image_name.removesuffix('.squashfs'), f"{incus_name}/opt/run-deploy/image/{image_dir}/"
    ], check=True)
else:
    subprocess.run([
        "incus", "file", "push", "--uid", "0", "--gid", "0", to_exec, f"{incus_name}/opt/run-deploy/image/{image_dir}/"
    ], check=True)

# Blame
pathlib.Path(f"{image_name.removesuffix('.squashfs')}.blame").write_text(f"{getpass.getuser()}@{socket.gethostname()}", 'utf-8')
subprocess.run([
    "incus", "file", "push", "--uid", "0", "--gid", "0", f"{image_name.removesuffix('.squashfs')}.blame", f"{incus_name}/opt/run-deploy/image/{image_dir}/"
], check=True)

# Exec
subprocess.run([
    "incus", "exec", incus_name, "--", f"/opt/run-deploy/image/{image_dir}/{image_name.removesuffix('.squashfs')}"
], check=True)

os.chdir('..')
shutil.rmtree(f"{image_name.removesuffix('.squashfs')}")
os.rmdir(mnt_point)