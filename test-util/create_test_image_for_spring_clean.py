#!/usr/bin/env python3
import os
import pathlib

os.chdir("/opt/run-deploy/images")

for dir_name in range(5):
    dir_name = f"run-deploy-test-{dir_name:02}"
    os.makedirs(dir_name, exist_ok=True)
    for image_name in range(50):
        image_name = f"{dir_name}/run-deploy-test-{image_name:02}"
        pathlib.Path(image_name).write_text("test", 'utf-8')
        pathlib.Path(f"{image_name}.blame").write_text("test", 'utf-8')
        pathlib.Path(f"{image_name}.squashfs").write_text("test", 'utf-8')
