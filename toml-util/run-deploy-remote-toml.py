#!/usr/bin/env python3
import argparse
import getpass
import json
import os
import pathlib
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

def key_validation(value: str):
    valid = not set(value).difference(string.ascii_letters + string.digits + '-_@')
    if not valid:
        error_and_exit(
            "KEY_REF_VALIDATION",
            f"'key_ref.txt' must be `ascii letters + digits + -_@`"
        )

key_ref = f"{getpass.getuser()}@{socket.gethostname()}"
if os.path.exists(os.path.expanduser("~/.config/run-deploy/key_ref.txt")):
    key_ref = pathlib.Path(os.path.expanduser("~/.config/run-deploy/key_ref.txt")).read_text('utf-8').strip()
    key_validation(key_ref)


parser = argparse.ArgumentParser(description="Process TOML based deploy")

parser.add_argument("toml")
parser.add_argument("--image-arg", action='append')
parser.add_argument("--ssh")
parser.add_argument("--ssh-metal")
parser.add_argument("--list-revision", action='store_true')
parser.add_argument("--last-deploy", action='store_true')
parser.add_argument("--last-deploy-blame", action='store_true')
parser.add_argument("--revert", metavar="REVISION")

args = parser.parse_args()

arg_toml = args.toml
flag_image_arg = args.image_arg
flag_ssh = args.ssh
flag_ssh_metal = args.ssh_metal
flag_list_revision = args.list_revision
flag_last_deploy = args.last_deploy
flag_last_deploy_blame = args.last_deploy_blame
flag_revert = args.revert


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


@dataclass(frozen=True)
class MinisignPasswd:
    passwd: str|None = None

    @classmethod
    def create(cls) -> Self:
        if os.path.exists(os.path.expanduser("~/.config/run-deploy/options/minisign_passwd")):
            return cls(passwd=getpass.getpass("Minisign Password:").strip())

        return cls()

    def passwdInput(self) -> bytes|None:
        if not self.passwd:
            return None
        return self.passwd.encode('utf-8')

    def environment(self) -> dict:
        d = {}
        if self.passwd:
            d["RUN_DEPLOY_MINISIGN_PASSWD_PIPE"] = "1"
        return d | os.environ


passwd = MinisignPasswd.create()

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
        match data:
            case {"image": str(), "create_image_script": str(), "ssh": dict()}:
                pass
            case _:
                raise DeployDataError("Must have 'image'(str), 'create_image_script'(str) and 'ssh'(dict)")

        image_name = data["image"]
        file_name_validation(image_name, "image", True)

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
            create_image_script=os.path.abspath(data["create_image_script"]),
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

toml_manifest = None

remote_cli = "run-deploy-remote-cli"
remote_deploy = "/opt/run-deploy/bin/run-deploy"


process_error_message = "Did you check that you got the SSH Private Key in the agent? Does `minisign.key` require a password? =D"


# List revision
if flag_list_revision:
    try:
        print("-- Listing Revision -- ", file=sys.stderr)
        for ssh_address, ssh_config in deploy_data.ssh_configs.items():
            print(f"-- Revision: {ssh_address}", file=sys.stderr)
            current_remote_cli = remote_cli
            if ssh_config.is_metal:
                current_remote_cli = "run-deploy-remote-metal-cli"
            extra = []
            if ssh_config.incus_name:
                extra += ["--incus", ssh_config.incus_name]
            subprocess.run([
                current_remote_cli, ssh_address, "list-revision", "--image", deploy_data.image_name
            ]+extra, check=True, input=passwd.passwdInput(), env=passwd.environment())
    except subprocess.CalledProcessError as e:
        print(process_error_message, file=sys.stderr)
        exit(e.returncode)

    exit(0)


# List last deploy
if flag_last_deploy:
    try:
        print("-- Listing Last Deploy -- ", file=sys.stderr)
        for ssh_address, ssh_config in deploy_data.ssh_configs.items():
            print(f"-- Last Deploy: {ssh_address}", file=sys.stderr)
            current_remote_cli = remote_cli
            if ssh_config.is_metal:
                current_remote_cli = "run-deploy-remote-metal-cli"
            extra = []
            if ssh_config.incus_name:
                extra += ["--incus", ssh_config.incus_name]
            subprocess.run([
                current_remote_cli, ssh_address, "last-deploy", "--image", deploy_data.image_name
            ]+extra, check=True, input=passwd.passwdInput(), env=passwd.environment())
    except subprocess.CalledProcessError as e:
        print(process_error_message, file=sys.stderr)
        exit(e.returncode)

    exit(0)


# List last deploy blame
if flag_last_deploy_blame:
    try:
        print("-- Listing Last Deploy Blame -- ", file=sys.stderr)
        for ssh_address, ssh_config in deploy_data.ssh_configs.items():
            print(f"-- Last Deploy Blame: {ssh_address}", file=sys.stderr)
            current_remote_cli = remote_cli
            if ssh_config.is_metal:
                current_remote_cli = "run-deploy-remote-metal-cli"
            extra = []
            if ssh_config.incus_name:
                extra += ["--incus", ssh_config.incus_name]
            subprocess.run([
                current_remote_cli, ssh_address, "last-deploy-blame", "--image", deploy_data.image_name
            ]+extra, check=True, input=passwd.passwdInput(), env=passwd.environment())
    except subprocess.CalledProcessError as e:
        print(process_error_message, file=sys.stderr)
        exit(e.returncode)

    exit(0)


# Bulk revert
if flag_revert:
    file_name_validation(flag_revert, "flag_revert", True)
    try:
        print("-- Performing Bulk Revert -- ", file=sys.stderr)
        for ssh_address, ssh_config in deploy_data.ssh_configs.items():
            print(f"-- Last Deploy Blame: {ssh_address}", file=sys.stderr)
            current_remote_cli = remote_cli
            if ssh_config.is_metal:
                current_remote_cli = "run-deploy-remote-metal-cli"
            extra = []
            if ssh_config.incus_name:
                extra += ["--incus", ssh_config.incus_name]
            subprocess.run([
                current_remote_cli, ssh_address, "revert", "--image", deploy_data.image_name, "--revision", flag_revert
            ]+extra, check=True, input=passwd.passwdInput(), env=passwd.environment())
    except subprocess.CalledProcessError as e:
        print(process_error_message, file=sys.stderr)
        exit(e.returncode)

    exit(0)


try:
    print("-- Checking Permission --", file=sys.stderr)
    fail = False
    for ssh_address, ssh_config in deploy_data.ssh_configs.items():
        print(f"-- Checking {ssh_address} --", file=sys.stderr)
        current_remote_cli = remote_cli
        if ssh_config.is_metal:
            current_remote_cli = "run-deploy-remote-metal-cli"
        extra = []
        if ssh_config.incus_name:
            extra += ["--incus", ssh_config.incus_name]
        permission_data = subprocess.run([
            current_remote_cli, ssh_address, "permission-json", "--image", deploy_data.image_name
        ]+extra, check=True, capture_output=True, input=passwd.passwdInput(), env=passwd.environment()).stdout.decode('utf-8')
        permission_data = json.loads(permission_data)
        has_full_permission = permission_data.get("full", False)
        if has_full_permission:
            print("Result: OK", file=sys.stderr)
        else:
            fail=True
            print("Result: FAIL", file=sys.stderr)
    if fail:
        exit(101)
except subprocess.CalledProcessError as e:
    print(e.output.decode('utf-8'), file=sys.stderr)
    print(process_error_message, file=sys.stderr)
    exit(e.returncode)
except json.JSONDecodeError:
    error_and_exit("JSON_PERMISSION", "Unable to decode permission")

last_deploy = ""
try:
    top_ssh_address = str(list(deploy_data.ssh_configs.keys())[0])
    top_ssh = deploy_data.ssh_configs[top_ssh_address]
    top_remote_cli = remote_cli
    if top_ssh.is_metal:
        top_remote_cli = "run-deploy-remote-metal-cli"

    extra = []
    if top_ssh.incus_name:
        extra += ["--incus", top_ssh.incus_name]

    # Get the last deploy
    last_deploy = subprocess.run([
        top_remote_cli, top_ssh_address, "last-deploy", "--image", deploy_data.image_name,
    ]+extra, check=True, capture_output=True, input=passwd.passwdInput(), env=passwd.environment()).stdout.decode('utf-8').strip()
except subprocess.CalledProcessError as e:
    print(e.output.decode('utf-8'), file=sys.stderr)
    exit(e.returncode)

if last_deploy:
    print(f"-- Last deploy is: {last_deploy}", file=sys.stderr)

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
    extra = []
    if os.path.exists(os.path.expanduser("~/.config/run-deploy/minisign.key")):
        extra += ['-s', os.path.expanduser("~/.config/run-deploy/minisign.key")]
    subprocess.run([
        "minisign", "-S",
    ] + extra + [ "-m", image_name ], check=True, capture_output=True, input=passwd.passwdInput())
except subprocess.CalledProcessError:
    error_and_exit(
        "IMAGE_SIGNING",
        "Unable sign image, does it need a password?"
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
            f"{key_ref}"
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
        extra = []
        if ssh_config.incus_name:
            extra += ["--incus", ssh_config.incus_name]
        subprocess.run([
            current_remote_cli, ssh_address, "revert", "--image", deploy_data.image_name, "--revision", last_deploy
        ]+extra, check=True, input=passwd.passwdInput(), env=passwd.environment())

# Finally remove the image from tmp.
shutil.rmtree(image_dir)
