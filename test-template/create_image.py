#!/usr/bin/env python3
import argparse
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import time


parser = argparse.ArgumentParser(description="Create test image")
parser.add_argument("--hostname", required=True)
args = parser.parse_args()

hostname = args.hostname

project_path = os.path.dirname(os.path.abspath(__file__))

tmp_dir = f"/tmp/test_template-{time.time()}"
os.mkdir(tmp_dir, mode=0o700)
os.chdir(tmp_dir)

shutil.copytree(f"{project_path}/mnt", "mnt")

now = datetime.datetime.now(datetime.UTC)
script_name = f"test-{now.year}-{now.month:02d}-{now.day:02d}_{now.hour:02d}-{now.minute:02d}-{now.second:02d}"
squashfs_name = f"{script_name}.squashfs"

script_path = pathlib.Path(f"mnt/_deploy/{script_name}")
script_path.write_text(f"""#!/bin/dash
cd /opt/run-deploy/image/test
ln -sf {squashfs_name} test.squashfs || exit 1
/opt/local/script/deploy/test
""", 'utf-8')
script_path.chmod(0o755)

script_path = pathlib.Path(f"mnt/_deploy/init_script")
script_path.write_text(f"""#!/bin/dash
cd /opt/run-deploy/image/test
ln -sf {squashfs_name} test.squashfs || exit 1
echo "Init: {squashfs_name} has been deployed"
""", 'utf-8')
script_path.chmod(0o755)

manifest_json = {
    hostname: {
        'incus-name': 'test',
        'image-dir': 'test',
        'exec': 'init_script',
        'stamp': now.timestamp(),
    }
}

with open("mnt/_deploy/push.json", "w") as f:
    json.dump(manifest_json, f)

subprocess.run([
    "mksquashfs", "mnt", squashfs_name, "-all-root", "-comp", "zstd"
], check=True, capture_output=True)
shutil.rmtree("mnt")

print(os.path.realpath(squashfs_name))