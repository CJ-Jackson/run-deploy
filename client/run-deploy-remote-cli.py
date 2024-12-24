#!/usr/bin/env python3
import getpass
import os
import pathlib
import random
import socket
import string
import subprocess
import sys

ssh_address = ""
try:
    ssh_address = sys.argv[1].strip()
except IndexError:
    print("Must have ssh address", file=sys.stderr)
    exit(1)

token_ref = ''.join(random.choice(string.ascii_letters+string.digits) for x in range(64))
token_file_name = f"/tmp/run-deploy-token-{token_ref}"
pathlib.Path(token_file_name).write_bytes(os.urandom(2048))

subprocess.run([
    "minisign", "-Sm", token_file_name
], check=True, capture_output=True)

subprocess.run([
    "scp", token_file_name, f"{token_file_name}.minisig", f"{ssh_address}:/tmp/run-deploy"
], check=True, capture_output=True)
os.remove(token_file_name)
os.remove(f"{token_file_name}.minisig")

env_token = f"RUN_DEPLOY_TOKEN={token_ref}"
env_key = f"RUN_DEPLOY_KEY='{getpass.getuser()}@{socket.gethostname()}'"

try:
    subprocess.run([
        "ssh", ssh_address, "--", env_token, env_key, "doas", "/opt/run-deploy/bin/run-deploy-cli"
    ] + sys.argv[2:], check=True)
except subprocess.CalledProcessError as e:
    exit(e.returncode)