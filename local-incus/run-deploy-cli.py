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
except:
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
    case "list-revision":
        revision = subprocess.run([
            "incus", "exec", incus_name, "--", "sh", "-c", f"ls -1a {image_path}/*.squashfs"
        ], capture_output=True, check=True).stdout.decode('utf-8').strip().splitlines()
        revision.pop()
        for index in range(len(revision)):
            revision[index] = os.path.basename(revision[index]).removesuffix('.squashfs')
        revision = list(reversed(revision))
        for rev in revision:
            print(rev)