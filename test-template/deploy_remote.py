#!/usr/bin/env python3
import getpass
import os
import shutil
import socket
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

hostname = ""
ssh_address = ""
try:
    hostname = sys.argv[1].strip()
    ssh_address = sys.argv[2].strip()
except IndexError:
    print("Need server hostname and ssh address", file=sys.stderr)
    exit(1)

last_deploy = ""
try:
    # Get the edition
    edition = subprocess.run([
        "run-deploy-remote-cli", ssh_address, "edition"
    ], check=True, capture_output=True).stdout.decode('utf-8').strip()

    # Get the last deploy
    if edition == "remote-incus":
        last_deploy = subprocess.run([
            "run-deploy-remote-cli", ssh_address, "last-deploy", "--incus", "test", "--image", "test",
        ], check=True, capture_output=True).stdout.decode('utf-8').strip()
    else:
        last_deploy = subprocess.run([
            "run-deploy-remote-cli", ssh_address, "last-deploy", "--image", "test",
        ], check=True, capture_output=True).stdout.decode('utf-8').strip()
except subprocess.CalledProcessError as e:
    print(e.output.decode('utf-8'), file=sys.stderr)
    exit(e.returncode)

# Create the image
image_name = subprocess.run([
    "./create_image.py", hostname
], check=True, capture_output=True).stdout.decode('utf-8').strip()

# Sign the image with the private key, so it can verified by the server with the corresponding public key.
subprocess.run([
    "minisign", "-Sm", image_name
], check=True, capture_output=True)

# Upload the image and the signature
subprocess.run([
    "scp", image_name, f"{image_name}.minisig", f"{ssh_address}:/tmp/run-deploy"
], check=True)

# Use ssh to tell the server to deploy the image, if that fails, it will automatically revert.
# `username@hostname` is for the server to cherry pick the correct public key.
try:
    subprocess.run([
        "ssh", ssh_address, "--", "doas", "/opt/run-deploy/bin/run-deploy",
        f"/tmp/run-deploy/{os.path.basename(image_name)}", f"{getpass.getuser()}@{socket.gethostname()}"
    ], check=True)
except subprocess.CalledProcessError as e:
    if e.returncode == 101:
        shutil.rmtree(os.path.dirname(image_name))
        exit(101)
    if edition == "remote-incus":
        last_deploy = subprocess.run([
            "run-deploy-remote-cli", ssh_address, "revert", "--incus", "test", "--image", "test", "--revision", last_deploy
        ], check=True)
    else:
        last_deploy = subprocess.run([
            "run-deploy-remote-cli", ssh_address, "revert", "--image", "test", "--revision", last_deploy
        ], check=True)

# Finally remove the image from tmp.
shutil.rmtree(os.path.dirname(image_name))