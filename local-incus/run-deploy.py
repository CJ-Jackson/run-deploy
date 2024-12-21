#!/usr/bin/env python3
import getpass
import json
import os.path
import shutil
import socket
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

if not image_name.endswith(".squashfs"):
    print("Image name must end with '.squashfs'", file=sys.stderr)
    exit(1)

os.chdir(base_dir)

mnt_point = f"/tmp/deploy-mount-{time.time()}"
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

data = {}
with open("push.json", "r", encoding='utf-8') as f:
    data = json.load(f)

data = data[socket.gethostname()]

incus_name: str = data['incus-name'].strip()
image_dir: str = data['image-dir'].strip()
copy_map: dict = data.get('map', {})
files_to_push: dict = data['files']
to_exec: str = data['exec'].strip()

# Sanity check
valid = True
if '/' in incus_name or '/' in to_exec or '/' in image_dir:
    valid = False
for src, dest in copy_map.items():
    if '/' in src or '/' in dest:
        valid = False
for file in files_to_push:
    if '/' in file or image_dir not in file:
        valid = False
if '/' in to_exec:
    valid = False

if not valid:
    print("Cannot have '/' in values, also image directory name must also be in file.", file=sys.stderr)
    exit(1)

# Copy files
for src, dest in copy_map.items():
    shutil.copy(src.strip(), dest.strip())

# Push files
for file in files_to_push:
    subprocess.run([
        "incus", "file", "push", "--uid", "0", "--gid", "0", file.strip(), f"{incus_name}/opt/image/{image_dir}/"
        ], check=True)

# Copy Exec (Enforce name convention)
if to_exec != image_name.removesuffix('.squashfs'):
    shutil.copy(to_exec, image_name.removesuffix('.squashfs'))
    subprocess.run([
        "incus", "file", "push", "--uid", "0", "--gid", "0", image_name.removesuffix('.squashfs'), f"{incus_name}/opt/image/{image_dir}/"
    ], check=True)

# Exec
subprocess.run([
    "incus", "exec", incus_name, "--", f"/opt/image/{image_dir}/{image_name.removesuffix('.squashfs')}"
], check=True)

os.chdir('..')
shutil.rmtree(f"{image_name.removesuffix('.squashfs')}")
os.rmdir(mnt_point)