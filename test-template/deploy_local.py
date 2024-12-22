#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

hostname = ""
try:
    hostname = sys.argv[1].strip()
except IndexError:
    print("Need server hostname", file=sys.stderr)
    exit(1)

# Create the image
image_name = subprocess.run([
    "./create_image.py", hostname
], check=True, capture_output=True).stdout.decode('utf-8').strip()

# Deploy the image
subprocess.run([
    "/opt/run-deploy/bin/run-deploy", image_name
], check=True)

shutil.rmtree(os.path.dirname(image_name))