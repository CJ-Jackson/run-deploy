#!/usr/bin/env python3
import getpass
import os
import shutil
import sys

if getpass.getuser() != "root":
    print("Must be root!", file=sys.stderr)
    exit(1)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

shutil.copy("run-deploy-image-toml.py", "/usr/local/bin/run-deploy-image-toml")
shutil.copy("run-deploy-local-toml.py", "/usr/local/bin/run-deploy-local-toml")
shutil.copy("run-deploy-remote-toml.py", "/usr/local/bin/run-deploy-remote-toml")