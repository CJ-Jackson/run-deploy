#!/usr/bin/env python3
import getpass
import os
import pathlib
import random
import socket
import string
import subprocess
import sys
import json

ssh_address = ""
try:
    ssh_address = sys.argv[1].strip()
except IndexError:
    print("Must have ssh address", file=sys.stderr)
    exit(1)

def error_and_exit(error_name: str, message: str):
    json.dump({"error_name": error_name, "message": message}, sys.stderr, indent="\t")
    exit(100)


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

token_ref = ''.join(random.choice(string.ascii_letters+string.digits) for x in range(64))
token_file_name = f"/tmp/run-deploy-token-{token_ref}"
pathlib.Path(token_file_name).write_bytes(os.urandom(2048))

extra = []
if os.path.exists(os.path.expanduser("~/.config/run-deploy/minisign.key")):
    extra += ['-s', os.path.expanduser("~/.config/run-deploy/minisign.key")]
subprocess.run([
    "minisign", "-S",
] + extra + [ "-m", token_file_name ], check=True, capture_output=True)

subprocess.run([
    "scp", f"{token_file_name}.minisig", token_file_name, f"{ssh_address}:/tmp/run-deploy"
], check=True, capture_output=True)
os.remove(token_file_name)
os.remove(f"{token_file_name}.minisig")

env_token = f"RUN_DEPLOY_TOKEN={token_ref}"
env_key = f"RUN_DEPLOY_KEY='{key_ref}'"

try:
    subprocess.run([
        "ssh", ssh_address, "--", env_token, env_key, "doas", "/opt/run-deploy/bin/run-deploy-metal-cli"
    ] + sys.argv[2:], check=True)
except subprocess.CalledProcessError as e:
    exit(e.returncode)