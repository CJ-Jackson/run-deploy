#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import time

arg_cmd = sys.argv[1]
commands: dict = {}


def handle_recv_fifo(fifo_path: str):
    while not os.path.exists(fifo_path):
        time.sleep(1)
    with open(fifo_path, "r") as fifo:
        data = json.load(fifo)
    if data["stderr"]:
        print(data["stderr"], file=sys.stderr)
    if data["stdout"]:
        print(data["stdout"])
    exit(data["code"])


def create_recv_fifo_add_to_queue() -> str:
    fifo_path = f"/tmp/run-deploy-recv-fifo-{time.time()}"
    if not os.path.exists(fifo_path):
        os.mkfifo(fifo_path, 0o666)

    pathlib.Path(f"/tmp/run-deploy-{time.time()}-queue").write_text(fifo_path, "utf-8")

    # Trigger systemd oneshot
    pathlib.Path("/tmp/run-deploy.path").touch()

    return fifo_path


def send_cli(cmd: str = "cli"):
    fifo_recv_path = f"/tmp/run-deploy-{cmd}-fifo-{time.time()}"

    data = {
        "cmd": cmd,
        "token": os.environ['RUN_DEPLOY_TOKEN'].strip(),
        "key": os.environ['RUN_DEPLOY_KEY'].strip(),
        "args": sys.argv[2:],
        "fifo": fifo_recv_path
    }

    fifo_path = create_recv_fifo_add_to_queue()

    with open(fifo_path, "w") as fifo:
        json.dump(data, fifo)
        fifo.flush()

    os.remove(fifo_path)

    handle_recv_fifo(fifo_recv_path)


def send_cli_metal():
    send_cli("cli-metal")


commands["cli"] = send_cli
commands["cli-metal"] = send_cli_metal


def deploy(cmd: str = "deploy"):
    fifo_recv_path = f"/tmp/run-deploy-{cmd}-fifo-{time.time()}"

    data = {
        "cmd": cmd,
        "target": sys.argv[2].strip(),
        "key": sys.argv[3].strip(),
        "fifo": fifo_recv_path
    }

    fifo_path = create_recv_fifo_add_to_queue()

    with open(fifo_path, "w") as fifo:
        json.dump(data, fifo)
        fifo.flush()

    os.remove(fifo_path)

    handle_recv_fifo(fifo_recv_path)


def deploy_metal():
    deploy("deploy-metal")


commands["deploy"] = deploy
commands["deploy-metal"] = deploy_metal


def handle_subprocess(fifo_path: str, args: list, env=None):
    if env is None:
        env = {}
    process = subprocess.run(args, env=env|os.environ, capture_output=True)
    with open(fifo_path, "w") as fifo:
        json.dump({
            "code": process.returncode,
            "stdout": process.stdout.decode('utf-8').strip(),
            "stderr": process.stderr.decode('utf-8').strip()
        }, fifo)
        fifo.flush()


def process_queue(recv_fifo_path: str):
    if not os.path.exists(recv_fifo_path):
        time.sleep(1)
        return
    with open(recv_fifo_path, "r") as fifo:
        data = json.load(fifo)
    fifo_path = data["fifo"]
    os.mkfifo(fifo_path, 0o666)
    match data:
        case {"cmd": "cli"}:
            handle_subprocess(fifo_path, ["/opt/run-deploy/bin/run-deploy-cli"] + data['args'], {
                "RUN_DEPLOY_TOKEN": data['token'],
                "RUN_DEPLOY_KEY": data['key']
            })
        case {"cmd": "cli-metal"}:
            handle_subprocess(fifo_path, ["/opt/run-deploy/bin/run-deploy-metal-cli"] + data['args'], {
                "RUN_DEPLOY_TOKEN": data['token'],
                "RUN_DEPLOY_KEY": data['key']
            })
        case {"cmd": "deploy"}:
            handle_subprocess(fifo_path, ["/opt/run-deploy/bin/run-deploy", data["target"], data["key"]])
        case {"cmd": "deploy-metal"}:
            handle_subprocess(fifo_path, ["/opt/run-deploy/bin/run-deploy-metal", data["target"], data["key"]])
    time.sleep(1)
    os.remove(fifo_path)


def recv():
    for queue in pathlib.Path("/tmp").glob("run-deploy-*-queue"):
        fifo_path = pathlib.Path(str(queue)).read_text('utf-8').strip()
        os.remove(str(queue))
        process_queue(fifo_path)



commands["recv"] = recv

try:
    commands[arg_cmd]()
except KeyError:
    print("Could not find command", file=sys.stderr)
