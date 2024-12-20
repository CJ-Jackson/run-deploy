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

# Get the last deploy
last_deploy = subprocess.run([
    "run-deploy-remote-cli", ssh_address, "test", "test", "last-deploy"
], check=True, capture_output=True).stdout.decode('utf-8').strip()

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
    "scp", image_name, f"{image_name}.minisig", f"{ssh_address}:/tmp"
], check=True)

# Use ssh to tell the server to deploy the image, if that fails, it will automatically revert.
# `username@hostname` is for the server to cherry pick the correct public key.
try:
    subprocess.run([
        "ssh", ssh_address, "--", "doas", "/opt/local/bin/run-deploy",
        f"/tmp/{os.path.basename(image_name)}", f"{getpass.getuser()}@{socket.gethostname()}"
    ], check=True)
except subprocess.CalledProcessError:
    last_deploy = subprocess.run([
        "run-deploy-remote-cli", ssh_address, "test", "test", "revert", last_deploy
    ], check=True)

# Finally remove the image from tmp.
shutil.rmtree(os.path.dirname(image_name))