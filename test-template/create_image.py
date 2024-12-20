#!/usr/bin/env python3
import datetime
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

hostname = ""
try:
    hostname = sys.argv[1].strip()
except IndexError:
    print("Need server hostname", file=sys.stderr)
    exit(1)

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
cd /opt/image/test
ln -sf {squashfs_name} test.squashfs || exit 1
/opt/local/script/deploy/test
""", 'utf-8')
script_path.chmod(0o755)

script_path = pathlib.Path(f"mnt/_deploy/init_{script_name}")
script_path.write_text(f"""#!/bin/dash
cd /opt/image/test
ln -sf {squashfs_name} test.squashfs || exit 1
echo "Init: {squashfs_name} has been deployed"
""", 'utf-8')
script_path.chmod(0o755)

manifest_json = {
    hostname: {
        'incus-name': 'test',
        'image-dir': 'test',
        'map': {f"init_{script_name}": script_name},
        'files': [script_name, squashfs_name],
        'exec': script_name
    }
}

with open("mnt/_deploy/push.json", "w") as f:
    json.dump(manifest_json, f)

subprocess.run([
    "mksquashfs", "mnt", squashfs_name, "-all-root", "-comp", "zstd"
], check=True, capture_output=True)
shutil.rmtree("mnt")

print(os.path.realpath(squashfs_name))