#!/usr/bin/env python3
import json
import os
import socket
import sys
import time

arg_cmd = sys.argv[1]
commands: dict = {}


def handle_fifo(fifo_path: str):
    with open(fifo_path, "r") as fifo:
        data = json.load(fifo)
        if data["code"] > 0:
            print(data["stderr"], file=sys.stderr)
            exit(data["code"])
        else:
            print(data["stdout"])
    os.remove(fifo_path)


def send_cli():
    fifo_path = f"/tmp/run-deploy-cli-fifo-{time.time()}"
    os.mkfifo(fifo_path, 0o666)

    data = {
        "cmd": "cli",
        "token": os.environ['RUN_DEPLOY_TOKEN'].strip(),
        "key": os.environ['RUN_DEPLOY_KEY'].strip(),
        "args": sys.argv[2:],
        "fifo": fifo_path
    }

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect("/tmp/run-deploy.sock")
        client.sendall(bytes(json.dumps(data) + "\n", 'utf-8'))

    handle_fifo(fifo_path)


commands["cli"] = send_cli


def deploy():
    fifo_path = f"/tmp/run-deploy-fifo-{time.time()}"
    os.mkfifo(fifo_path, 0o666)

    data = {
        "cmd": "deploy",
        "target": sys.argv[2].strip(),
        "key": sys.argv[3].strip(),
        "fifo": fifo_path
    }

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect("/tmp/run-deploy.sock")
        client.sendall(bytes(json.dumps(data) + "\n", 'utf-8'))

    handle_fifo(fifo_path)


commands["deploy"] = deploy


def recv():
    data = json.load(sys.stdin)
    fifo_path = data["fifo"]
    with open(fifo_path, "w") as fifo:
        json.dump(data, fifo)


commands["recv"] = recv

try:
    commands[arg_cmd]()
except KeyError:
    print("Could not find command", file=sys.stderr)