#!/usr/bin/env python3
import argparse
import getpass
import os
import pathlib
import shutil
import sys

parser = argparse.ArgumentParser(description="Install toml util")
parser.add_argument("--uv", action='store_true', help="Place uv shebang on top of file")
args = parser.parse_args()

flag_uv = args.uv

if getpass.getuser() != "root":
    print("Must be root!", file=sys.stderr)
    exit(1)

os.chdir(os.path.dirname(os.path.abspath(__file__)))

uv_stub = None
if flag_uv:
    uv_stub = pathlib.Path("../uv_stub.py").read_text("utf-8").strip() + "\n"

def copy(src: str, dest: str):
    if uv_stub:
        src_str = pathlib.Path(src).read_text("utf-8").removeprefix("#!/usr/bin/env python3").strip()
        dest_str = f'{uv_stub}{src_str}' + "\n"
        pathlib.Path(dest).write_text(dest_str, 'utf-8')
    else:
        shutil.copy(src, dest)

copy("run-deploy-image-toml.py", "/usr/local/bin/run-deploy-image-toml")
copy("run-deploy-local-toml.py", "/usr/local/bin/run-deploy-local-toml")
copy("run-deploy-remote-toml.py", "/usr/local/bin/run-deploy-remote-toml")