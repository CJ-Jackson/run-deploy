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

base_dir = ""
image_name = ""
minisign_public_key_path = ""
key_ref = ""
try:
    target_path = sys.argv[1].strip()
    key_ref = sys.argv[2].strip()

    base_dir = os.path.dirname(target_path)
    image_name = os.path.basename(target_path)
    minisign_public_key_path = f"/opt/run-deploy/minisign/{key_ref}.pub"
except IndexError:
    print("Must have two argument", file=sys.stderr)
    exit(1)

if not image_name.endswith(".squashfs"):
    print("Image name must end with '.squashfs'", file=sys.stderr)
    exit(1)

os.chdir(base_dir)

try:
    subprocess.run(["minisign", "-Vqm", image_name, "-p", minisign_public_key_path], check=True)
    os.remove(f"{image_name}.minisig")
except subprocess.CalledProcessError:
    print(f"Invalid signature for '{image_name}'", file=sys.stderr)
    os.remove(image_name)
    os.remove(f"{image_name}.minisig")
    exit(1)


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
shutil.move(image_name, f"{image_name.removesuffix('.squashfs')}/{image_name}")

os.chdir(image_name.removesuffix('.squashfs'))

data = {}
with open("push.json", "r", encoding='utf-8') as f:
    data = json.load(f)

data = data[socket.gethostname()]

incus_name: str = data['incus-name'].strip()
image_dir: str = data['image-dir'].strip()
to_exec: str = data['exec'].strip()

# Sanity check
valid = True
if '/' in incus_name or '/' in to_exec or '/' in image_dir:
    valid = False

if not valid:
    print("Cannot have '/' in values, also image directory name must also be in image file.", file=sys.stderr)
    exit(1)

# Create directory if not exist
subprocess.run([
    "incus", "exec", incus_name, "--", "mkdir", "-p", f"/opt/run-deploy/image/{image_dir}"
], capture_output=True)

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
pathlib.Path(f"{image_name.removesuffix('.squashfs')}.blame").write_text(key_ref, 'utf-8')
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