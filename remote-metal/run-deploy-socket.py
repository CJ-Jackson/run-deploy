#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import time

arg_cmd = sys.argv[1]
commands: dict = {}


def handle_fifo(fifo_path: str):
    with open(fifo_path, "r") as fifo:
        data = json.load(fifo)
    if data["code"] > 0:
        print(data["stderr"], file=sys.stderr)
    else:
        print(data["stdout"])
    os.remove(fifo_path)
    exit(data["code"])


def send_cli():
    fifo_path = "/tmp/run-deploy.fifo"
    if not os.path.exists(fifo_path):
        os.mkfifo(fifo_path, 0o666)

    fifo_recv_path = f"/tmp/run-deploy-cli-fifo-{time.time()}"
    os.mkfifo(fifo_recv_path, 0o666)

    data = {
        "cmd": "cli",
        "token": os.environ['RUN_DEPLOY_TOKEN'].strip(),
        "key": os.environ['RUN_DEPLOY_KEY'].strip(),
        "args": sys.argv[2:],
        "fifo": fifo_recv_path
    }

    pathlib.Path("/tmp/run-deploy.path").touch()

    with open(fifo_path, "w") as fifo:
        json.dump(data, fifo)
        fifo.flush()

    handle_fifo(fifo_recv_path)


commands["cli"] = send_cli


def deploy():
    fifo_path = "/tmp/run-deploy.fifo"
    if not os.path.exists(fifo_path):
        os.mkfifo(fifo_path, 0o666)

    fifo_recv_path = f"/tmp/run-deploy-fifo-{time.time()}"
    os.mkfifo(fifo_recv_path, 0o666)

    data = {
        "cmd": "deploy",
        "target": sys.argv[2].strip(),
        "key": sys.argv[3].strip(),
        "fifo": fifo_recv_path
    }

    pathlib.Path("/tmp/run-deploy.path").touch()

    with open(fifo_path, "w") as fifo:
        json.dump(data, fifo)
        fifo.flush()

    os.remove(fifo_path)

    handle_fifo(fifo_recv_path)


commands["deploy"] = deploy


def handle_subprocess(fifo_path: str, args: list, env=None):
    if env is None:
        env = {}
    process = subprocess.run(args, env=env|os.environ, capture_output=True)
    with open(fifo_path, "w") as fifo:
        json.dump({
            "code": process.returncode,
            "stdout": process.stdout.decode('utf-8'),
            "stderr": process.stderr.decode('utf-8')
        }, fifo)
        fifo.flush()


def recv():
    if not os.path.exists("/tmp/run-deploy.fifo"):
        time.sleep(2)
        exit(0)
    with open("/tmp/run-deploy.fifo", "r") as fifo:
        data = json.load(fifo)
    fifo_path = data["fifo"]
    match data:
        case {"cmd": "cli"}:
            handle_subprocess(fifo_path, ["/opt/run-deploy/bin/run-deploy-cli"] + data['args'], {
                "RUN_DEPLOY_TOKEN": data['token'],
                "RUN_DEPLOY_KEY": data['key']
            })
        case {"cmd": "deploy"}:
            handle_subprocess(fifo_path, ["/opt/run-deploy/bin/run-deploy", data["target"], data["key"]])
    time.sleep(2)


commands["recv"] = recv

try:
    commands[arg_cmd]()
except KeyError:
    print("Could not find command", file=sys.stderr)
