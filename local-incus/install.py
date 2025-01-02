#!/usr/bin/env python3
import getpass
import os
import pathlib
import shutil
import sys

if getpass.getuser() != "root":
    print("Must be root!", file=sys.stderr)
    exit(1)

os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.makedirs("/opt/run-deploy/bin", exist_ok=True)
os.makedirs("/opt/run-deploy/options", exist_ok=True)

# Enable strict mode by default
pathlib.Path("/opt/run-deploy/options/strict").write_text("strict", 'utf-8')

shutil.copy("run-deploy.py", "/opt/run-deploy/bin/run-deploy")
shutil.copy("run-deploy-cli.py", "/opt/run-deploy/bin/run-deploy-cli")