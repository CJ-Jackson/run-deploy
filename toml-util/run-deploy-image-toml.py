#!/usr/bin/env python3
import argparse
import datetime
import json
import os.path
import pathlib
import shutil
import string
import subprocess
import sys
import time
import tomllib


def error_and_exit(error_name: str, message: str):
    json.dump({"error_name": error_name, "message": message}, sys.stderr, indent="\t")
    exit(100)


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


parser = argparse.ArgumentParser(description="Process TOML based image")
parser.add_argument("toml")
parser.add_argument("--hostname")

args = parser.parse_args()

arg_toml = args.toml
flag_hostname = args.hostname

toml_manifest = {}
try:
    with open(arg_toml, "rb") as f:
        toml_manifest = tomllib.load(f)
except (OSError, tomllib.TOMLDecodeError):
    error_and_exit(
        "TOML_MANIFEST",
        "Unable to open toml manifest"
    )

image_name = ""
try:
    image_name = toml_manifest["name"]
except KeyError:
    error_and_exit(
        "NO_NAME",
        "Must have a name"
    )
file_name_validation(image_name, "name", True)

build_script = ""
try:
    build_script = os.path.abspath(toml_manifest["build_script"])
except KeyError:
    error_and_exit(
        "BUILD_SCRIPT_MISSING",
        "`build_script` is required"
    )

manifest_json = toml_manifest.get("manifest", {})
if not manifest_json:
    error_and_exit(
        "JSON_MANIFEST",
        "Must have a manifest"
    )

try:
    if flag_hostname:
        manifest_json = {flag_hostname: manifest_json["__"]}
except KeyError:
    error_and_exit(
        "HOSTNAME_FLAG",
        "There isn't a flag set for either `flag_hostname`"
    )

project_path = os.path.dirname(os.path.abspath(arg_toml))
os.chdir(project_path)

tmp_dir = f"{toml_manifest.get('tmp_location', '/tmp')}/run-deploy-image-{image_name}-{time.time()}"
os.mkdir(tmp_dir, 0o700)
os.chdir(tmp_dir)
os.makedirs("mnt/_deploy")

now = datetime.datetime.now(datetime.UTC)
script_name = f"{image_name}-{now.year}-{now.month:02d}-{now.day:02d}_{now.hour:02d}-{now.minute:02d}-{now.second:02d}"
squashfs_name = f"{script_name}.squashfs"

script_path = pathlib.Path(f"mnt/_deploy/{script_name}")
script_path.write_text(f"""#!/bin/dash
cd /opt/run-deploy/image/{image_name}
ln -sf {squashfs_name} {image_name}.squashfs || exit 1
/opt/local/script/deploy/{image_name} || echo "/opt/run-deploy/script/deploy/{image_name} not found or incorrect permission!" && exit 0
""", 'utf-8')
script_path.chmod(0o755)

for key, _ in manifest_json.items():
    manifest_json[key]["image-dir"] = image_name
    manifest_json[key]["exec"] = script_name
    manifest_json[key]["stamp"] = now.timestamp()

with open("mnt/_deploy/push.json", "w") as f:
    json.dump(manifest_json, f)

# Run build script
try:
    subprocess.run([
        build_script
    ], check=True, env={"RUN_DEPLOY_PROJECT_PATH": project_path} | os.environ)
except subprocess.CalledProcessError:
    error_and_exit(
        "BUILD_SCRIPT",
        "Unable to run `build_script`"
    )
except FileNotFoundError:
    error_and_exit(
        "BUILD_SCRIPT_NOT_FOUND",
        "`build_script` is not found"
    )
except PermissionError:
    error_and_exit(
        "BUILD_SCRIPT_PERMISSION",
        "Does not have permission to run `build_script`"
    )

subprocess.run([
    "mksquashfs", "mnt", squashfs_name, "-all-root", "-comp", "zstd"
], check=True, capture_output=True)
shutil.rmtree("mnt")

print(os.path.realpath(squashfs_name))
