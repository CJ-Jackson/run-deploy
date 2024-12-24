#!/usr/bin/env python3
import argparse
import os.path
import subprocess
import sys

parser = argparse.ArgumentParser(description='Queries and operate run-deploy system')

command_arg_list = ', '.join([
    'edition',
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'incus-list',
    'image-list'
])
parser.add_argument('command',
                    help=f"Commands: {command_arg_list}")

incus_flag_list = ', '.join([
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert',
    'image-list'
])
parser.add_argument('--incus',
                    help=f"Required for: {incus_flag_list}")
image_flag_list = ', '.join([
    'last-deploy',
    'last-deploy-blame',
    'list-revision',
    'revert'
])
parser.add_argument('--image',
                    help=f"Required for: {image_flag_list}")
parser.add_argument('--revision', help="Required for: revert")

args = parser.parse_args()

incus_name = args.incus
image_ref = args.image
command_ref = args.command
revision_name = args.revision


def validate_input_image_incus():
    if image_ref is None or incus_name is None:
        print(f"'--incus' and '--image' are required for command: {command_ref}", file=sys.stderr)
        exit(102)
    if '/' in image_ref or '/' in incus_name:
        print("'--incus' and '--image' must not have /", file=sys.stderr)
        exit(102)


def validate_input_incus():
    if incus_name is None:
        print(f"'--incus' is required for command: {command_ref}", file=sys.stderr)
        exit(102)
    if '/' in incus_name:
        print("'--incus' must not have /", file=sys.stderr)
        exit(102)


def validate_input_revision():
    if revision_name is None:
        print(f"'--revision' is required for command: {command_ref}", file=sys.stderr)
        exit(102)
    if '/' in revision_name:
        print("'--revision' must not have /", file=sys.stderr)
        exit(102)


def get_image_path():
    return f"/opt/run-deploy/image/{image_ref}"


match command_ref:
    case "edition":
        print("local-incus")
    case "last-deploy":
        validate_input_image_incus()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "realpath", f"{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        print(os.path.basename(last_path))
    case "last-deploy-blame":
        validate_input_image_incus()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "realpath", f"{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        blame = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "cat", f"{os.path.basename(last_path)}.blame"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip()
        print(blame)
    case "list-revision":
        validate_input_image_incus()
        image_path = get_image_path()
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "realpath", f"{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        last_path = os.path.basename(last_path)
        revision = subprocess.run([
            "incus", "exec", incus_name, "--cwd", image_path, "--", "sh", "-c",
            "for f in *.blame; do (echo \"${f}:$(cat ${f})\";); done"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().splitlines()
        for index in range(len(revision)):
            revision_data = str(revision[index]).split(':')
            blame = revision_data.pop()
            revision_name = ':'.join(revision_data).removesuffix('.blame')
            current = ""
            if revision_name == last_path:
                current = "     *CURRENT*"
            revision[index] = f"{revision_name}   blame: {blame}{current}"
        revision.sort()
        revision = list(reversed(revision))
        for rev in revision:
            print(rev)
    case "revert":
        validate_input_image_incus()
        validate_input_revision()
        image_path = get_image_path()
        subprocess.run([
            "incus", "exec", incus_name, "--", f"{image_path}/{revision_name}"
        ], check=True)
    case "incus-list":
        subprocess.run([
            "incus", "list", "-c", "n", "-f", "csv"
        ])
    case "image-list":
        validate_input_incus()
        try:
            images = subprocess.run([
                "incus", "exec", incus_name, "--cwd", "/opt/run-deploy/image", "--", "ls", "-1A"
            ], check=True, capture_output=True).stdout.decode('utf-8').strip().splitlines()
            images.sort()
            for image in images:
                print(image)
        except subprocess.CalledProcessError:
            print("")
    case _:
        print(f"Command `{command_ref}` was not found!", file=sys.stderr)
        exit(103)
