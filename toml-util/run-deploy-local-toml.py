#!/usr/bin/env python3
import argparse
import json
import os
import shutil
import string
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from typing import Self

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
        if "=" not in image_arg:
            error_and_exit(
                "NO_EQUAL_IN_IMAGE_ARG",
                "'image' must have a '=' sign"
            )
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

os.chdir(os.path.dirname(os.path.abspath(arg_toml)))


class DeployDataError(Exception): pass


@dataclass(frozen=True)
class DeployData:
    incus_name: str
    image_name: str
    create_image_script: str
    pre_script: tuple = ()


    @classmethod
    def create(cls, data: dict) -> Self:
        if "incus" not in data:
            raise DeployDataError("Must have 'incus'")
        incus_name = data["incus"]
        file_name_validation(incus_name, "incus", True)

        if "image" not in data:
            raise DeployDataError("Must have 'image'")
        image_name = data["image"]
        file_name_validation(image_name, "image", True)

        if "create_image_script" not in data:
            raise DeployDataError("Must have 'create_image_script'")
        create_image_script = os.path.abspath(data["create_image_script"])

        pre_script = data.get("pre_script", [])
        for key in range(len(pre_script)):
            pre_script[key] = os.path.abspath(pre_script[key])

        return cls(
            incus_name=incus_name,
            image_name=image_name,
            create_image_script=create_image_script,
            pre_script=tuple(pre_script)
        )

deploy_data = None
try:
    deploy_data = DeployData.create(toml_manifest)
except DeployDataError as e:
    error_and_exit("DEPLOY_DATA_ERROR", e.__str__())
if not deploy_data:
    exit(0)

local_cli = "run-deploy-cli"
local_deploy = "/opt/run-deploy/bin/run-deploy"

last_deploy = ""

try:
    last_deploy = subprocess.run([
        local_cli, "last-deploy", "--incus", deploy_data.incus_name, "--image", deploy_data.image_name,
    ], check=True, capture_output=True).stdout.decode('utf-8').strip()
except subprocess.CalledProcessError as e:
    print(e.output.decode('utf-8'), file=sys.stderr)
    exit(e.returncode)

# Pre Script
try:
    for script in list(deploy_data.pre_script):
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
        deploy_data.create_image_script
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
    subprocess.run([
        local_cli, "revert", "--incus", deploy_data.incus_name, "--image", deploy_data.image_name,
        "--revision",
        last_deploy
    ], check=True)

# Finally remove the image from tmp.
shutil.rmtree(image_dir)
