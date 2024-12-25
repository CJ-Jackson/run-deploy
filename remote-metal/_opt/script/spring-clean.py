#!/usr/bin/env python3
import argparse
import os.path
import pathlib
import subprocess
import time

parser = argparse.ArgumentParser(description="Clean out older deply and keep the last defined amount")

parser.add_argument("--keep", default=20, help="The amount of last deploy to keep")
parser.add_argument("--real-run", action='store_true')

args = parser.parse_args()

arg_keep = int(args.keep)
arg_real_run = args.real_run

images = {}
unsorted_images = pathlib.Path("/opt/run-deploy/images").glob("*/*.blame")
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

files_to_delete = []
for image in images_to_delete:
    image = str(image)
    files_to_delete.append(f"rm '{image}'")
    files_to_delete.append(f"rm '{image.removesuffix('.blame')}'")
    files_to_delete.append(f"rm '{image.removesuffix('.blame')}.squashfs'")

files_to_delete = "\n".join(files_to_delete)

script = f"""#!/bin/sh

{files_to_delete}"""

if not arg_real_run:
    print(script)
    exit(0)

script_name = f"/tmp/run-deploy-spring-clean-metal-{time.time()}"
script_path = pathlib.Path(script_name)
script_path.write_text(script, 'utf-8')
script_path.chmod(0o700)

subprocess.run([
    script_name
], check=True)