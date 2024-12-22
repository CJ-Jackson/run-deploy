#!/usr/bin/env python3
import datetime
import os.path
import pathlib
import shutil
import subprocess
import time
import tomllib

toml_config = """
# Which edition to you want to create the installer image for?
edition = "local-incus"

# User account to create to use for deployment
deploy_user = "deploy"

# Place public keys here
ssh_authorized_keys = []
""".strip()

toml_config_filename = f"/tmp/run-deploy-installer-config-{time.time()}"
with open(toml_config_filename, "w", encoding="utf-8") as f:
    print(toml_config, file=f)

subprocess.run([
    "nvim", toml_config_filename
])

with open(toml_config_filename, "rb") as f:
    toml_config = tomllib.load(f)

os.remove(toml_config_filename)

current_path = os.path.dirname(os.path.abspath(__file__))

tmp_dir = f"/tmp/run-deploy-installer-{time.time()}"
os.mkdir(tmp_dir)
os.chmod(tmp_dir, 0o700)
os.chdir(tmp_dir)

os.mkdir("opt")

shutil.copytree(f"{current_path}/_opt", "opt/run-deploy")
os.mkdir("opt/run-deploy/bin")
os.mkdir("opt/run-deploy/etc")
os.mkdir("opt/run-deploy/minisign")
os.mkdir("opt/run-deploy/ssh")
os.mkdir("opt/run-deploy/script/deploy")

shutil.copy(f"{current_path}/{toml_config['edition']}/run-deploy.py", "opt/run-deploy/bin/run-deploy")
shutil.copy(f"{current_path}/{toml_config['edition']}/run-deploy-cli.py", "opt/run-deploy/bin/run-deploy-cli")
os.chmod("opt/run-deploy/bin/run-deploy", 0o700)
os.chmod("opt/run-deploy/bin/run-deploy-cli", 0o700)

doas = pathlib.Path("opt/run-deploy/etc/doas.conf")
doas.write_text(f"""
permit nopass {toml_config['deploy_user']} as root cmd /opt/local/bin/run-deploy
permit nopass setenv {{ RUN_DEPLOY_TOKEN RUN_DEPLOY_KEY }} {toml_config['deploy_user']} as root cmd /opt/local/bin/run-deploy-cli
""".strip(), 'utf-8')
doas.chmod(0o400)

update = pathlib.Path("update.sh")
update.write_text("""#!/bin/dash
cp -p opt/run-deploy/bin/run-deploy /opt/run-deploy/bin/run-deploy
cp -p opt/run-deploy/bin/run-deploy-cli /opt/run-deploy/bin/run-deploy-cli
""", 'utf-8')
update.chmod(0o755)

install = pathlib.Path("install.sh")
install.write_text(f"""#!/bin/dash
# Copy opt
cp -rp opt/run-deploy /opt

# Setup system service
ln -s /opt/run-deploy/systemd/system/run-deploy-permission.path /etc/systemd/system/run-deploy-permission.path
ln -s /opt/run-deploy/systemd/system/run-deploy-permission.service /etc/systemd/system/run-deploy-permission.service
systemctl enable run-deploy-permission.path
systemctl start run-deploy-permission.path

# Add user and harden home directory, and copy authorized_keys
useradd -m -s /bin/dash {toml_config['deploy_user']}
chown root:{toml_config['deploy_user']}  /home/{toml_config['deploy_user']} /home/{toml_config['deploy_user']}/* 2> /dev/null
chmod 750 /home/{toml_config['deploy_user']}
chmod 640 /home/{toml_config['deploy_user']}/*
mkdir /home/{toml_config['deploy_user']}/.ssh
chown root:{toml_config['deploy_user']} /home/{toml_config['deploy_user']}/.ssh
chmod 750 /home/{toml_config['deploy_user']}/.ssh
cp /opt/run-deploy/ssh/authorized_keys /home/{toml_config['deploy_user']}/.ssh
chown root:{toml_config['deploy_user']} /home/{toml_config['deploy_user']}/.ssh/authorized_keys

# Copy doas
chmod 600 /etc/doas.conf 2> /dev/null
cat /opt/run-deploy/etc/doas.conf >> /etc/doas.conf
chmod 400 /etc/doas.conf

exit 0
""", 'utf-8')
install.chmod(0o755)

authorized_keys = ""
for key in toml_config['ssh_authorized_keys']:
    authorized_keys += f"{key}\n"
key_path = pathlib.Path("opt/run-deploy/ssh/authorized_keys")
key_path.write_text(authorized_keys, 'utf-8')
key_path.chmod(0o640)

os.chdir('..')

now = datetime.datetime.now(datetime.UTC)
squashfs_name = f"run-deploy-installer-{toml_config['edition']}-{now.year}-{now.month:02d}-{now.day:02d}_{now.hour:02d}-{now.minute:02d}-{now.second:02d}.squashfs"

subprocess.run([
    "mksquashfs", tmp_dir, squashfs_name, "-all-root", "-comp", "zstd"
], check=True, capture_output=True)

shutil.rmtree(tmp_dir)
print(os.path.realpath(squashfs_name))