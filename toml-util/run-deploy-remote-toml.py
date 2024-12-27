#!/usr/bin/env python3
import argparse
import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import tomllib


def error_and_exit(error_name: str, message: str):
    json.dump({"error_name": error_name, "message": message}, sys.stderr, indent="\t")
    exit(100)


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
        return_args += f"--{image_arg}".split("=", maxsplit=2)
    return return_args


toml_manifest = {}
try:
    with open(arg_toml, "rb") as f:
        toml_manifest = tomllib.load(f)
except (OSError, tomllib.TOMLDecodeError):
    error_and_exit(
        "TOML_MANIFIEST",
        "Unable to open toml manifest"
    )

os.chdir(os.path.dirname(os.path.abspath(arg_toml)))

ssh = toml_manifest.get("ssh", {})
if not ssh:
    error_and_exit(
        "SSH",
        "Must have an ssh config!"
    )

try:
    if flag_ssh:
        ssh = {flag_ssh: ssh["__"]}
    elif flag_ssh_metal:
        ssh = {flag_ssh_metal: ssh["__metal"]}
except KeyError:
    error_and_exit(
        "SSH_FLAG",
        "There isn't a flag set for either `flag_ssh` or `flag_ssh_metal`"
    )

remote_cli = "run-deploy-remote-cli"
remote_deploy = "/opt/run-deploy/bin/run-deploy"

last_deploy = ""

try:
    top_ssh_address = str(list(ssh.keys())[0])
    top_ssh = ssh[top_ssh_address]
    top_remote_cli = remote_cli
    if top_ssh.get("metal", False):
        top_remote_cli = "run-deploy-remote-metal-cli"

    # Get the last deploy
    if top_ssh.get("incus", None):
        last_deploy = subprocess.run([
            remote_cli, top_ssh_address, "last-deploy", "--incus", top_ssh["incus"], "--image", top_ssh["image"],
        ], check=True, capture_output=True).stdout.decode('utf-8').strip()
    else:
        last_deploy = subprocess.run([
            top_remote_cli, top_ssh_address, "last-deploy", "--image", top_ssh["image"],
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
    print(e)
    print(os.getcwd())
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
    for ssh_address, ssh_config in ssh.items():
        subprocess.run([
            "scp", f"{image_name}.minisig", image_name, f"{ssh_address}:{ssh_config.get('upload', '/tmp/run-deploy')}"
        ], check=True)
except subprocess.CalledProcessError:
    error_and_exit(
        "IMAGE_UPLOAD",
        "Failed to upload image"
    )

base_image_name = os.path.basename(image_name)
image_dir = os.path.dirname(image_name)

try:
    for ssh_address, ssh_config in ssh.items():
        current_remote_deploy = remote_deploy
        if ssh_config.get("metal", False):
            current_remote_deploy = "/opt/run-deploy/bin/run-deploy-metal"
        output = subprocess.run([
            "ssh", ssh_address, "--", "doas", current_remote_deploy,
            f"{ssh_config.get('upload', '/tmp/run-deploy')}/{base_image_name}", f"{getpass.getuser()}@{socket.gethostname()}"
        ], check=True, capture_output=True).stdout.decode('utf-8')
        print(output)
except subprocess.CalledProcessError as e:
    outerr = e.stderr.decode('utf-8')
    print(outerr, file=sys.stderr)
    if e.returncode != 100 or json.loads(outerr).get("error_name", "") != "EXEC_FAIL":
        shutil.rmtree(image_dir)
        exit(e.returncode)
    for ssh_address, ssh_config in ssh.items():
        current_remote_cli = remote_cli
        if ssh_config.get("metal", False):
            current_remote_cli = "run-deploy-remote-metal-cli"
        if ssh_config.get("incus", None):
            last_deploy = subprocess.run([
                remote_cli, ssh_address, "revert", "--incus", ssh_config["incus"], "--image", ssh_config["image"], "--revision",
                last_deploy
            ], check=True)
        else:
            last_deploy = subprocess.run([
                current_remote_cli, ssh_address, "revert", "--image", ssh_config["image"], "--revision", last_deploy
            ], check=True)

# Finally remove the image from tmp.
shutil.rmtree(image_dir)