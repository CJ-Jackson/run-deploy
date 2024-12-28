#!/usr/bin/env python3
import argparse
import getpass
import json
import os
import shutil
import socket
import string
import subprocess
import sys
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


parser = argparse.ArgumentParser(description="Process TOML based deploy")

parser.add_argument("toml")
parser.add_argument("--image-arg", action='append')

args = parser.parse_args()

arg_toml = args.toml
flag_image_arg = args.image_arg


def image_args() -> list:
    return_args = []
    if flag_image_arg is None:
        return return_args
    for image_arg in flag_image_arg:
        return_args += f"--{image_arg}".split("=", maxsplit=2)
    return return_args


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
incus_name = ""
try:
    image_name = toml_manifest["image"]
    incus_name = toml_manifest["incus"]
    file_name_validation(image_name, "image_name", True)
    file_name_validation(incus_name, "incus_name", True)
except KeyError:
    error_and_exit(
        "IMAGE_INCUS_REQUIRED",
        "'image' and 'incus' are required"
    )

os.chdir(os.path.dirname(os.path.abspath(arg_toml)))

local_cli = "run-deploy-cli"
local_deploy = "/opt/run-deploy/bin/run-deploy"

last_deploy = ""

try:
    last_deploy = subprocess.run([
        local_cli, "last-deploy", "--incus", incus_name, "--image", image_name,
    ], check=True, capture_output=True).stdout.decode('utf-8').strip()
except subprocess.CalledProcessError as e:
    print(e.output.decode('utf-8'), file=sys.stderr)
    exit(e.returncode)

# Pre Script
try:
    for script in toml_manifest.get('pre_script', []):
        subprocess.run([
            script
        ], check=True)
except (subprocess.CalledProcessError, FileNotFoundError, PermissionError):
    error_and_exit(
        "PRE_SCRIPT",
        "Unable to execute at least one prescript."
    )

# Create Image
image_name = ""
try:
    image_name = subprocess.run([
        toml_manifest.get("create_image_script")
    ] + image_args(), check=True, capture_output=True).stdout.decode('utf-8').strip()
except (subprocess.CalledProcessError, FileNotFoundError, PermissionError) as e:
    error_and_exit(
        "IMAGE_CREATION",
        "Unable to execute image script"
    )

image_dir = os.path.dirname(image_name)

try:
    print(f"-- Deploying --", file=sys.stderr)
    process_data = subprocess.run([
        local_deploy, image_name
    ], check=True, capture_output=True)
    output = process_data.stdout.decode('utf-8').strip()
    if output:
        print(output)
    outerr = process_data.stderr.decode('utf-8').strip()
    if outerr:
        print(outerr)
except subprocess.CalledProcessError as e:
    outerr = e.stderr.decode('utf-8')
    print(outerr, file=sys.stderr)
    if e.returncode != 100 or json.loads(outerr).get("error_name", "") != "EXEC_FAIL":
        shutil.rmtree(image_dir)
        exit(e.returncode)
    last_deploy = subprocess.run([
        local_cli, "revert", "--incus", incus_name, "--image", image_name,
        "--revision",
        last_deploy
    ], check=True)

# Finally remove the image from tmp.
shutil.rmtree(image_dir)
