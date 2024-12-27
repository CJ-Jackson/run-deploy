#!/usr/bin/env python3
import argparse
import json
import os.path
import string
import subprocess
import sys


def error_and_exit(error_name: str, message: str):
    json.dump({"error_name": error_name, "message": message}, sys.stderr, indent="\t")
    exit(100)


parser = argparse.ArgumentParser(description='Queries and operate run-deploy system')

command_arg_list = ', '.join([
    'edition',
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'list-incus',
    'list-image'
])
parser.add_argument('command', help=f"Commands: {command_arg_list}")
incus_flag_list = ', '.join([
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'list-image'
])
parser.add_argument('--incus', help=f"Required for: {incus_flag_list}")
image_flag_list = ', '.join([
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert'
])
parser.add_argument('--image', help=f"Required for: {image_flag_list}")
parser.add_argument('--revision', help="Required for: revert")

args = parser.parse_args()

arg_command = args.command
flag_incus = args.incus
flag_image = args.image
flag_revision = args.revision

def file_name_validation(value: str, name: str, flag: bool=False):
    extra = '.-_'
    if flag:
        extra = '-_'
    valid = not set(value).difference(string.ascii_letters + string.digits + extra)
    if not valid:
        error_and_exit(
            "FILE_NAME_VALIDATION",
            f"{name} must be `ascii letters + digits + {extra}`"
        )


def validate_input_image_incus():
    if flag_image is None or flag_incus is None:
        error_and_exit(
            "FLAG_VALIDATION",
            f"'--incus' and '--image' are required for command: {arg_command}"
        )
    file_name_validation(flag_image, "flag_image", True)
    file_name_validation(flag_incus, "flag_incus", True)


def validate_input_incus():
    if flag_incus is None:
        error_and_exit(
            "FLAG_VALIDATION",
            f"'--incus' is required for command: {arg_command}"
        )
    file_name_validation(flag_incus, "flag_incus", True)


def validate_input_revision():
    if flag_revision is None:
        error_and_exit(
            "FLAG_VALIDATION",
            f"'--revision' is required for command: {arg_command}"
        )
    file_name_validation(flag_revision, "flag_revision", True)


def get_image_path():
    return f"/opt/run-deploy/image/{flag_image}"


match arg_command:
    case "edition":
        print("local-incus")
    case "last-deploy":
        validate_input_image_incus()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", flag_incus, "--cwd", image_path, "--", "realpath", f"{flag_image}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        print(os.path.basename(last_path))
    case "last-deploy-blame":
        validate_input_image_incus()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", flag_incus, "--cwd", image_path, "--", "realpath", f"{flag_image}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        blame = subprocess.run([
            "incus", "exec", flag_incus, "--cwd", image_path, "--", "cat", f"{os.path.basename(last_path)}.blame"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip()
        print(blame)
    case "list-revision":
        validate_input_image_incus()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", flag_incus, "--cwd", image_path, "--", "realpath", f"{flag_image}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        last_path = os.path.basename(last_path)
        revision = subprocess.run([
            "incus", "exec", flag_incus, "--cwd", image_path, "--", "sh", "-c",
            "for f in *.blame; do (echo \"${f}:$(cat ${f})\";); done"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().splitlines()
        for index in range(len(revision)):
            revision_data = str(revision[index]).split(':')
            blame = revision_data.pop()
            flag_revision = ':'.join(revision_data).removesuffix('.blame')
            current = ""
            if flag_revision == last_path:
                current = "     *CURRENT*"
            revision[index] = f"{flag_revision}   blame: {blame}{current}"
        revision.sort()
        revision = list(reversed(revision))
        for rev in revision:
            print(rev)
    case "revert":
        validate_input_image_incus()
        validate_input_revision()
        image_path = get_image_path()
        subprocess.run([
            "incus", "exec", flag_incus, "--", f"{image_path}/{flag_revision}"
        ], check=True)
    case "list-incus":
        subprocess.run([
            "incus", "list", "-c", "n", "-f", "csv"
        ])
    case "list-image":
        validate_input_incus()
        try:
            images = subprocess.run([
                "incus", "exec", flag_incus, "--cwd", "/opt/run-deploy/image", "--", "ls", "-1A"
            ], check=True, capture_output=True).stdout.decode('utf-8').strip().splitlines()
            images.sort()
            for image in images:
                print(image)
        except subprocess.CalledProcessError:
            print("")
    case _:
        error_and_exit(
            "COMMAND_NOT_FOUND",
            f"Command `{arg_command}` was not found!"
        )
