#!/usr/bin/env python3
import os.path
import subprocess
import sys

incus_name = ""
image_ref = ""
command_ref = ""
try:
    incus_name = sys.argv[1]
    image_ref = sys.argv[2]
    command_ref = sys.argv[3]
except IndexError:
    print("Must have incus_name, image_ref and command_ref", file=sys.stderr)
    exit(1)

if '/' in image_ref or '/' in incus_name:
    print("Incus name and image Ref must not have /", file=sys.stderr)

image_path = f"/opt/image/{image_ref}"

match command_ref:
    case "last-deploy":
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--", "realpath", f"{image_path}/{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        print(os.path.basename(last_path))
    case "last-deploy-blame":
        last_path = subprocess.run([
            "incus", "exec", incus_name, "--", "realpath", f"{image_path}/{image_ref}.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().removesuffix('.squashfs')
        blame = subprocess.run([
            "incus", "exec", incus_name, "--", "cat", f"{last_path}.blame"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip()
        print(blame)
    case "list-revision":
        revision = subprocess.run([
            "incus", "exec", incus_name, "--", "sh", "-c", f"ls -1a {image_path}/*.blame"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().splitlines()
        for index in range(len(revision)):
            revision_name = str(revision[index]).removesuffix('.blame')
            blame = subprocess.run([
                "incus", "exec", incus_name, "--", "cat", f"{revision_name}.blame"
            ], check=True, capture_output=True).stdout.decode('utf-8').strip()
            revision[index] = f"{os.path.basename(revision_name)}   blame: {blame}"
        revision = list(reversed(revision))
        for rev in revision:
            print(rev)
    case "revert":
        revision_name = ""
        try:
            revision_name = sys.argv[4]
        except IndexError:
            print("Must have revision name", file=sys.stderr)
            exit(2)
        if '/' in revision_name:
            print("Revision name must not have /", file=sys.stderr)
            exit(2)
        subprocess.run([
            "incus", "exec", incus_name, "--", f"{image_path}/{revision_name}"
        ])