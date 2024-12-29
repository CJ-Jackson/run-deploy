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
parser.add_argument("--ssh")
parser.add_argument("--ssh-metal")

args = parser.parse_args()

arg_toml = args.toml
flag_image_arg = args.image_arg
flag_ssh = args.ssh
flag_ssh_metal = args.ssh_metal


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


class SSHConfigError(Exception): pass


@dataclass(frozen=True)
class SSHConfig:
    incus_name: str
    is_metal: bool
    upload: str = "/tmp/run-deploy"

    @classmethod
    def create(cls, data: dict) -> Self:
        incus_name = data.get("incus", "")
        if incus_name:
            file_name_validation(incus_name, "incus", True)
        return cls(
            incus_name=incus_name,
            upload=data.get("upload", "/tmp/run-deploy"),
            is_metal=data.get("metal", False)
        )


@dataclass(frozen=True)
class DeployData:
    image_name: str
    create_image_script: str
    ssh_configs: dict[str, SSHConfig]
    pre_script: tuple = ()

    @classmethod
    def create(cls, data: dict) -> Self:
        if "image" not in data:
            raise DeployDataError("Must have 'image'")
        image_name = data["image"]
        file_name_validation(image_name, "image", True)

        if "create_image_script" not in data:
            raise DeployDataError("Must have 'create_image_script'")
        create_image_script = os.path.abspath(data["create_image_script"])

        if "ssh" not in data:
            raise SSHConfigError("Must have at least one SSH config")
        ssh_configs = data["ssh"]
        for key, value in ssh_configs.items():
            ssh_configs[key] = SSHConfig.create(value)

        if flag_ssh or flag_ssh_metal:
            try:
                if flag_ssh:
                    ssh_configs = {flag_ssh: ssh_configs['__']}
                elif flag_ssh_metal:
                    ssh_configs = {flag_ssh_metal: ssh_configs['__metal']}
            except KeyError:
                raise SSHConfigError("There isn't a flag set for either `flag_ssh` or `flag_ssh_metal`")

        pre_script = data.get("pre_script", [])
        for key in range(len(pre_script)):
            pre_script[key] = os.path.abspath(pre_script[key])

        return cls(
            image_name=image_name,
            create_image_script=create_image_script,
            ssh_configs=ssh_configs,
            pre_script=tuple(pre_script)
        )


deploy_data = None
try:
    deploy_data = DeployData.create(toml_manifest)
except DeployDataError as e:
    error_and_exit("DEPLOY_DATA_ERROR", e.__str__())
except SSHConfigError as e:
    error_and_exit("SSH_CONFIG_ERROR", e.__str__())
if not deploy_data:
    exit(0)

remote_cli = "run-deploy-remote-cli"
remote_deploy = "/opt/run-deploy/bin/run-deploy"

last_deploy = ""
try:
    top_ssh_address = str(list(deploy_data.ssh_configs.keys())[0])
    top_ssh = deploy_data.ssh_configs[top_ssh_address]
    top_remote_cli = remote_cli
    if top_ssh.is_metal:
        top_remote_cli = "run-deploy-remote-metal-cli"

    # Get the last deploy
    if top_ssh.incus_name:
        last_deploy = subprocess.run([
            remote_cli, top_ssh_address, "last-deploy", "--incus", top_ssh.incus_name, "--image", deploy_data.image_name,
        ], check=True, capture_output=True).stdout.decode('utf-8').strip()
    else:
        last_deploy = subprocess.run([
            top_remote_cli, top_ssh_address, "last-deploy", "--image", deploy_data.image_name,
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

# Sign the Image
try:
    subprocess.run([
        "minisign", "-Sm", image_name
    ], check=True, capture_output=True)
except subprocess.CalledProcessError:
    error_and_exit(
        "IMAGE_SIGNING",
        "Unable sign image"
    )

# Upload image
try:
    for ssh_address, ssh_config in deploy_data.ssh_configs.items():
        print(f"-- Uploading: {ssh_address} --", file=sys.stderr)
        subprocess.run([
            "scp", f"{image_name}.minisig", image_name, f"{ssh_address}:{ssh_config.upload}"
        ], check=True)
except subprocess.CalledProcessError:
    error_and_exit(
        "IMAGE_UPLOAD",
        "Failed to upload image"
    )

base_image_name = os.path.basename(image_name)
image_dir = os.path.dirname(image_name)

try:
    for ssh_address, ssh_config in deploy_data.ssh_configs.items():
        current_remote_deploy = remote_deploy
        if ssh_config.is_metal:
            current_remote_deploy = "/opt/run-deploy/bin/run-deploy-metal"
        print(f"-- Deploying: {ssh_address} --", file=sys.stderr)
        process_data = subprocess.run([
            "ssh", ssh_address, "--", "doas", current_remote_deploy,
            f"{ssh_config.upload}/{base_image_name}",
            f"{getpass.getuser()}@{socket.gethostname()}"
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
    for ssh_address, ssh_config in deploy_data.ssh_configs.items():
        current_remote_cli = remote_cli
        if ssh_config.is_metal:
            current_remote_cli = "run-deploy-remote-metal-cli"
        if ssh_config.incus_name:
            subprocess.run([
                remote_cli, ssh_address, "revert", "--incus", ssh_config.incus_name, "--image", deploy_data.image_name,
                "--revision",
                last_deploy
            ], check=True)
        else:
            subprocess.run([
                current_remote_cli, ssh_address, "revert", "--image", deploy_data.image_name, "--revision", last_deploy
            ], check=True)

# Finally remove the image from tmp.
shutil.rmtree(image_dir)
