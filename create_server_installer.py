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
# ( remote-incus, remote-metal )
edition = "remote-incus"

# User account to create to use for deployment
deploy_user = "deploy"

# Place public keys here
ssh_authorized_keys = []

# Use uv
uv = false

# The format is TOML
""".strip()

toml_config_filename = f"/tmp/run-deploy-installer-config-{time.time()}.toml"
with open(toml_config_filename, "w", encoding="utf-8") as f:
    print(toml_config, file=f)

subprocess.run([
    os.environ.get("EDITOR", "nano"), toml_config_filename
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
os.mkdir("opt/run-deploy/image")
os.mkdir("opt/run-deploy/bin")
os.mkdir("opt/run-deploy/etc")
os.mkdir("opt/run-deploy/exec")
os.mkdir("opt/run-deploy/minisign")
os.mkdir("opt/run-deploy/ssh")
os.mkdir("opt/run-deploy/script/deploy")
os.mkdir("opt/run-deploy/options")

# Enable strict mode by default
pathlib.Path("opt/run-deploy/options/strict").write_text("strict", 'utf-8')

uv_stub = None
if toml_config.get("uv", False):
    uv_stub = pathlib.Path(f"{current_path}/uv_stub.py").read_text("utf-8").strip() + "\n"


def copy(src: str, dest: str):
    if uv_stub and not dest.endswith("run-deploy-socket"):
        src_str = pathlib.Path(src).read_text("utf-8").removeprefix("#!/usr/bin/env python3").strip()
        dest_str = f'{uv_stub}{src_str}' + "\n"
        pathlib.Path(dest).write_text(dest_str, 'utf-8')
    else:
        shutil.copy(src, dest)


for run_deploy_path in pathlib.Path(f"{current_path}/{toml_config['edition']}").glob('*.py'):
    run_deploy_path = str(run_deploy_path)
    run_deploy_target_path = f"opt/run-deploy/bin/{os.path.basename(run_deploy_path).removesuffix('.py')}"
    copy(run_deploy_path, run_deploy_target_path)
    os.chmod(run_deploy_target_path, 0o700)
    if run_deploy_target_path.endswith("run-deploy-socket"):
        os.chmod(run_deploy_target_path, 0o755)

if os.path.exists(f"{current_path}/{toml_config['edition']}/_opt"):
    shutil.copytree(f"{current_path}/{toml_config['edition']}/_opt", "opt/run-deploy", dirs_exist_ok=True)

if uv_stub:
    for python_script in pathlib.Path("opt/run-deploy/script").glob("*.py"):
        python_script = str(python_script)
        copy(python_script, python_script)

pathlib.Path("opt/run-deploy/systemd/system/run-deploy-touch.service").write_text(f"""[Unit]
Description=Run-deploy init touch service

[Service]
Type=oneshot
User={toml_config['deploy_user']}
ExecStart=/usr/bin/touch /tmp/run-deploy.path
ExecStart=/usr/bin/mkdir /tmp/run-deploy-queue

[Install]
WantedBy=multi-user.target""", "utf-8")

systemd_symlinks = []
systemd_cmd = []
systemd_paths = pathlib.Path("opt/run-deploy/systemd/system").glob("run-deploy-*")
for systemd_name in systemd_paths:
    systemd_name = os.path.basename(str(systemd_name))
    systemd_symlinks.append(
        f"ln -s '/opt/run-deploy/systemd/system/{systemd_name}' '/etc/systemd/system/{systemd_name}'"
    )
    if systemd_name.endswith(".timer") or systemd_name.endswith(".path") or systemd_name.endswith("touch.service"):
        systemd_cmd.append(f"systemctl enable '{systemd_name}'")
        systemd_cmd.append(f"systemctl start '{systemd_name}'")
systemd_symlinks = "\n".join(systemd_symlinks)
systemd_cmd = "\n".join(systemd_cmd)

update = pathlib.Path("update.sh")
update.write_text("""#!/bin/dash
cp -p opt/run-deploy/bin/* /opt/run-deploy/bin
""", 'utf-8')
update.chmod(0o755)

install = pathlib.Path("install.sh")
install.write_text(f"""#!/bin/dash
# Copy opt
cp -rp opt/run-deploy /opt

# Add user and harden home directory, and copy authorized_keys
useradd -m -s /bin/dash {toml_config['deploy_user']}
chown root:{toml_config['deploy_user']} /home/{toml_config['deploy_user']} /home/{toml_config['deploy_user']}/.* 2> /dev/null
chmod 750 /home/{toml_config['deploy_user']}
chmod 640 /home/{toml_config['deploy_user']}/.* 2> /dev/null
mkdir /home/{toml_config['deploy_user']}/.ssh
chown root:{toml_config['deploy_user']} /home/{toml_config['deploy_user']}/.ssh
chmod 750 /home/{toml_config['deploy_user']}/.ssh
cp /opt/run-deploy/ssh/authorized_keys /home/{toml_config['deploy_user']}/.ssh
chown root:{toml_config['deploy_user']} /home/{toml_config['deploy_user']}/.ssh/authorized_keys

# Setup system service
{systemd_symlinks}
{systemd_cmd}

exit 0
""", 'utf-8')
install.chmod(0o755)

key_path = pathlib.Path("opt/run-deploy/ssh/authorized_keys")
key_path.write_text("\n".join(toml_config['ssh_authorized_keys']) + "\n", 'utf-8')
key_path.chmod(0o640)

os.chdir('..')

now = datetime.datetime.now(datetime.UTC)
squashfs_name = f"run-deploy-installer-{toml_config['edition']}-{now.year}-{now.month:02d}-{now.day:02d}_{now.hour:02d}-{now.minute:02d}-{now.second:02d}.squashfs"

subprocess.run([
    "mksquashfs", tmp_dir, squashfs_name, "-all-root", "-comp", "zstd"
], check=True, capture_output=True)

shutil.rmtree(tmp_dir)
print(os.path.realpath(squashfs_name))
