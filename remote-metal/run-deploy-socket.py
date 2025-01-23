#!/usr/bin/env python3
import json
import os
import socket
import sys

arg_cmd = sys.argv[1]
commands: dict = {}

def send_cli():
    data = {
        "cmd": "cli",
        "token": os.environ['RUN_DEPLOY_TOKEN'].strip(),
        "key": os.environ['RUN_DEPLOY_KEY'].strip(),
        "args": sys.argv[2:]
    }

    rtn_data = {}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect("/tmp/run-deploy.sock")
        client.sendall(bytes(json.dumps(data) + "\n", 'utf-8'))
        client.accept()

        rtn_data = client.recv(1024)
    print(rtn_data)

commands["cli"] = send_cli


def deploy():
    data = {
        "cmd": "deploy",
        "target": sys.argv[2].strip(),
        "key": sys.argv[3].strip(),
    }

    rtn_data = {}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect("/tmp/run-deploy.sock")
        client.sendall(bytes(json.dumps(data) + "\n", 'utf-8'))

        rtn_data = client.recv(1024)
    print(rtn_data)


commands["deploy"] = deploy


def recv():
    data = json.load(sys.stdin)
    # json.dump(data, sys.stdout)
    sys.stdout.write(json.dumps(data) + 'rn')
    exit(0)


commands["recv"] = recv

try:
    commands[arg_cmd]()
except KeyError:
    print("Could not find command", file=sys.stderr)