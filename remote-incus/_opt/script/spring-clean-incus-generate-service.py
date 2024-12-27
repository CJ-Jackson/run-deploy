#!/usr/bin/env python3
import argparse
import getpass
import os
import pathlib
import subprocess
import sys

parser = argparse.ArgumentParser(description="Generate service file for spring-clean (incus)")
parser.add_argument("--incus", required=True)

args = parser.parse_args()

arg_incus = args.incus

if getpass.getuser() != "root":
    print("Must be root!", file=sys.stderr)
    exit(1)

service_name = f"/opt/run-deploy/systemd/system/run-deploy-spring-clean-incus-{arg_incus}.service"
timer_name = f"/opt/run-deploy/systemd/system/run-deploy-spring-clean-incus-{arg_incus}.timer"

pathlib.Path(service_name).write_text(f"""[Unit]
Description="Clean up old deploy from incus container ({arg_incus})"

[Service]
User=root
Type=oneshot
ExecStart=/opt/run-deploy/script/spring-clean.py --real-run --incus {arg_incus}
""", 'utf-8')

pathlib.Path(timer_name).write_text(f"""[Unit]
Description=Run spring-cleaner for run-deploy daily (incus: {arg_incus})

[Timer]
OnCalendar=daily
Persistent=true
AccuracySec=1us
RandomizedDelaySec=12h

[Install]
WantedBy=timers.target
""", 'utf-8')

os.symlink(service_name, f"/etc/systemd/system/{os.path.basename(service_name)}")
os.symlink(timer_name, f"/etc/systemd/system/{os.path.basename(timer_name)}")

subprocess.run([
    "systemctl", "enable", os.path.basename(timer_name)
], check=True)
subprocess.run([
    "systemctl", "start", os.path.basename(timer_name)
], check=True)

exec_path = pathlib.Path(f"/opt/run-deploy/exec/spring-clean-incus-{arg_incus}")
exec_path.write_text(f"""#!/bin/dash
systemctl start {os.path.basename(service_name)}""", 'utf-8')
exec_path.chmod(0o755)