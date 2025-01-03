#!/usr/bin/env python3
import argparse
import datetime
import json
import os.path
import pathlib
import shutil
import string
import subprocess
import sys
import time
import tomllib
from dataclasses import dataclass
from typing import Self


def error_and_exit(error_name: str, message: str):
    json.dump({"error_name": error_name, "message": message}, sys.stderr, indent="\t")
    exit(100)


def file_name_validation(value: str, name: str, flag: bool = False):
    extra = '.-_'
    if flag:
        extra = '-_'
    valid = not set(value).difference(string.ascii_letters + string.digits + extra)
    if not valid:
        error_and_exit(
            "FILE_NAME_VALIDATION",
            f"{name} must be `ascii letters + digits + {extra}`"
        )


parser = argparse.ArgumentParser(description="Process TOML based image")
parser.add_argument("toml")
parser.add_argument("--hostname")

args = parser.parse_args()

arg_toml = args.toml
flag_hostname = args.hostname

toml_manifest = {}
try:
    with open(arg_toml, "rb") as f:
        toml_manifest = tomllib.load(f)
except (OSError, tomllib.TOMLDecodeError):
    error_and_exit(
        "TOML_MANIFEST",
        "Unable to open toml manifest"
    )

project_path = os.path.dirname(os.path.abspath(arg_toml))
os.chdir(project_path)


class ManifestDataError(Exception): pass


class BuildDataError(Exception): pass


@dataclass()
class ManifestData:
    incus_name: str = ""
    image_dir: str = ""
    exec: str = ""
    stamp: float = 0

    @classmethod
    def create(cls, data: dict) -> Self:
        incus_name = incus_name = data.get("incus-name", "")
        if incus_name:
            file_name_validation(incus_name, "incus-name", True)
        return cls(incus_name)

    def make_json_dict(self) -> dict:
        if self.incus_name:
            return {
                "incus-name": self.incus_name,
                "image-dir": self.image_dir,
                "exec": self.exec,
                "stamp": self.stamp
            }
        else:
            return {
                "image-dir": self.image_dir,
                "exec": self.exec,
                "stamp": self.stamp
            }


@dataclass(frozen=True)
class BuildData:
    name: str
    build_script: str
    manifest: dict[str, ManifestData]
    tmp_locaiton: str = "/tmp"

    @classmethod
    def create(cls, data: dict) -> Self:
        match data:
            case {"manifest": dict(), "name": str(), "build_script": str()}:
                pass
            case _:
                raise ManifestDataError("Must have 'name'(str) 'manifest'(dict) and 'build_script'(str)")
        manifest = data["manifest"]
        for key, value in manifest.items():
            manifest[key] = ManifestData.create(value)

        if flag_hostname:
            if '__' not in manifest:
                raise ManifestDataError("Manifest is not setup for `--hostname`")
            manifest = {flag_hostname: manifest['__']}

        name = data["name"]
        file_name_validation(name, "name", True)

        return cls(
            name=name,
            build_script=os.path.abspath(data["build_script"]),
            manifest=manifest,
            tmp_locaiton=data.get("tmp_location", "/tmp")
        )

    def make_manifest_json_dict(self) -> dict:
        data = {}
        for key, value in self.manifest.items():
            data[key] = value.make_json_dict()
        return data

    def update_manifest(self, script_name: str, stamp: float):
        for _, value in self.manifest.items():
            value.image_dir = self.name
            value.exec = script_name
            value.stamp = stamp


build_data = None
try:
    build_data = BuildData.create(toml_manifest)
except ManifestDataError as e:
    error_and_exit("MANIFEST_DATA_ERROR", e.__str__())
except BuildDataError as e:
    error_and_exit("BUILD_DATA_ERROR", e.__str__())
if not build_data:
    exit(0)

toml_manifest = None

tmp_dir = f"{build_data.tmp_locaiton}/run-deploy-image-{build_data.name}-{time.time()}"
os.mkdir(tmp_dir, 0o700)
os.chdir(tmp_dir)
os.makedirs("mnt/_deploy")

now = datetime.datetime.now(datetime.UTC)
script_name = f"{build_data.name}-{now.year}-{now.month:02d}-{now.day:02d}_{now.hour:02d}-{now.minute:02d}-{now.second:02d}"
squashfs_name = f"{script_name}.squashfs"

script_path = pathlib.Path(f"mnt/_deploy/{script_name}")
script_path.write_text(f"""#!/bin/dash
cd /opt/run-deploy/image/{build_data.name}
ln -sf {squashfs_name} {build_data.name}.squashfs || exit 1
/opt/local/script/deploy/{build_data.name} || echo "/opt/run-deploy/script/deploy/{build_data.name} not found or incorrect permission!" && exit 0
""", 'utf-8')
script_path.chmod(0o755)

build_data.update_manifest(script_name, now.timestamp())

with open("mnt/_deploy/push.json", "w") as f:
    json.dump(build_data.make_manifest_json_dict(), f)

# Run build script
try:
    subprocess.run([
        build_data.build_script
    ], check=True, env={"RUN_DEPLOY_PROJECT_PATH": project_path} | os.environ)
except subprocess.CalledProcessError:
    error_and_exit(
        "BUILD_SCRIPT",
        "Unable to run `build_script`"
    )
except FileNotFoundError:
    error_and_exit(
        "BUILD_SCRIPT_NOT_FOUND",
        "`build_script` is not found"
    )
except PermissionError:
    error_and_exit(
        "BUILD_SCRIPT_PERMISSION",
        "Does not have permission to run `build_script`"
    )

subprocess.run([
    "mksquashfs", "mnt", squashfs_name, "-all-root", "-comp", "zstd"
], check=True, capture_output=True)
shutil.rmtree("mnt")

print(os.path.realpath(squashfs_name))
