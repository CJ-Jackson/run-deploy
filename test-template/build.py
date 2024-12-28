#!/usr/bin/env python3
import os
import shutil
import sys

project_path = ""
try:
    project_path = os.environ["RUN_DEPLOY_PROJECT_PATH"]
except KeyError:
    print("RUN_DEPLOY_PROJECT_PATH is missing", file=sys.stderr)
    exit(1)

shutil.copytree(f"{project_path}/mnt", "mnt", dirs_exist_ok=True)