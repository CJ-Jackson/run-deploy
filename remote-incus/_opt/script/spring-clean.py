#!/usr/bin/env python3
import argparse
import os.path
import pathlib
import subprocess
import time

parser = argparse.ArgumentParser(description="Clean out older deploy on incus container and keep the last defined amount")

parser.add_argument("--keep", default=20, help="The amount of last deploy to keep")
parser.add_argument("--real-run", action='store_true')
parser.add_argument("--incus", required=True)

args = parser.parse_args()

arg_keep = int(args.keep)
arg_real_run = args.real_run
arg_incus = args.incus

unsorted_images = []
try:
    unsorted_images = subprocess.run([
        "incus", "exec", arg_incus, "--", "sh", "-c", "for image in /opt/run-deploy/image/*/*.blame; do (echo ${image}); done"
    ], check=True, capture_output=True).stdout.decode('utf-8').strip().splitlines()
except subprocess.CalledProcessError:
    exit(0)

images = {}
for unsorted_image in unsorted_images:
    image_key = os.path.dirname(unsorted_image)
    if image_key not in images:
        images[image_key] = []
    images[image_key].append(unsorted_image)

images_to_delete = []
for _, image_list in images.items():
    image_list.sort()
    image_list = list(reversed(image_list))
    if len(image_list) > arg_keep:
        images_to_delete += image_list[arg_keep:]

if len(images_to_delete) == 0:
    exit(0)

files_to_delete = []
for image in images_to_delete:
    image = str(image)
    files_to_delete.append(f"rm '{image}'")
    files_to_delete.append(f"rm '{image.removesuffix('.blame')}'")
    files_to_delete.append(f"rm '{image.removesuffix('.blame')}.squashfs'")

if len(files_to_delete) == 0:
    exit(0)

files_to_delete = "\n".join(files_to_delete)

script = f"""#!/bin/sh

{files_to_delete}"""

if not arg_real_run:
    print(script)
    exit(0)

script_name = f"/tmp/run-deploy-spring-clean-incus-{arg_incus}-{time.time()}"
script_path = pathlib.Path(script_name)
script_path.write_text(script, 'utf-8')
script_path.chmod(0o700)

subprocess.run([
    "incus", "file", "push", script_name, f"{arg_incus}/tmp/"
], check=True)
subprocess.run([
    "incus", "exec", arg_incus, "--", script_name
], check=True)
os.remove(script_name)