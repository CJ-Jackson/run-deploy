# run-deploy

'run-deploy' is a daemonless and stateless deployment system that is quite simple, elegant and fun to use. It relies on
the following sane open-source solution.

* [SquashFS](https://en.wikipedia.org/wiki/SquashFS)
  * With the json manifest located inside the image `_deploy/push.json`
* [OpenDoas](https://wiki.archlinux.org/title/Doas)
  * To allow deploy user to run the script as root, it is a lot safer than SUDO and Polkit.
* [Minisign](https://jedisct1.github.io/minisign/)
  * For image and user verification, the public key is cherry picked by the client `username@hostname`, as mentioned
    earlier it a stateless system.
  * The image itself has to be signed by a private key.
  * It is a lightweight compared to GnuPG.
  * The public key goes into `/opt/run-deploy/minisign/username@hostname.pub`

## How it works

First you need a build script for image building, for now we create a dummy.

File: `build.py`
```python
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
```
Give it execute right `chmod 755 build.py`

Now we need to create the following
File: `create_image.toml`
```toml
#!/usr/bin/env run-deploy-image-toml

# Image name
name = "example"
# The location is relative to toml file
build_script = "./build.py"

# The hostname has to match the hostname of where it getting deployed
[manifest.hostname]
# Name of incus container
incus_name = "example"
```
Give it execute right `chmod 755 create_image.toml`
You can also test the image building by running `./create_image.toml`

Now we the toml file for deploy, this is for the local machine

File: `deploy_local.toml`
```toml
#!/usr/bin/env run-deploy-local-toml

# Image creation script to execute
create_image_script = "./create_image.toml"

incus = "example"
image = "example"
```
Give it execute right `chmod 755 deploy_local.toml`
Let deploy to local machine by running `./deploy_local.toml`

For remote deploy we need to create the following TOML.

File: `deploy_remote.toml`
```toml
#!/usr/bin/env run-deploy-remote-toml

# Image creation script to execute
create_image_script = "./create_image.toml"

# Image name (Mandatory)
image = "example"

# SSH Config, at least one is required
[ssh.'username@deploy.example-1.com']
# Mandatory for remote-incus
incus = "example"
```
Give it execute right `chmod 755 deploy_remote.toml`
Let deploy to remote machine by running `./deploy_remote.toml`

That is the jist of it. Really clean and elegant isn't it? =D

[Click here for more detail on toml-util](toml-util/README.md)

## Image Manifest

The squashfs image must have a manifest at `_deploy/push.json` otherwise it will not deploy. The structure of the
manifest looks like the following.

```json
{
  "server_hostname": {
    "incus-name": "container_name",
    "image-dir": "example",
    "exec": "script_to_copy_and_exec",
    "stamp": 123456
  }
}
```

For `remote-metal` edition you can omit `incus-name`, but is required for
`remote-incus` and `local-incus` edition :)

You can have as many hostname as you want.

`stamp` is optional.

## Dependencies

run-deploy currently has three editions.

### local-incus

* python3
* squashfuse

### remote-incus

* python3.11
* squashfuse
* doas
* dash
* minisign
* incus

### remote-metal

* python3.11
* squashfuse
* doas
* dash
* minisign

## Installation

### Remote client

Run `client/install.py` as root

### local-incus

Run `local-incus/install.py` as root

### toml-util

Run `toml-util/install.py` as root

Note: must install remote client

### For servers

Run `create_server_installer.py`, first it will open a toml file in the default text editor, edit it, add the ssh
authorized_key and if nessecary change the edition and deploy_user, it will create the user for you. Save it and it
should create a squashfs image.

You upload the image to the server to `/tmp`, do the following as root.

```shell
cd /tmp

mkdir mnt
mount run-deploy-installer-*.squashfs mnt

cd mnt
./install.sh
cd ..
umount mnt
```

Now all you need to do is create the private and public key pair, on the client machine run

```shell
mkdir ~/.config/run-deploy
cd ~/.config/run-deploy

minisign -G -p "$(whoami)@$(hostname).pub" -s 'minisign.key' -W
```

And upload the public key (`.pub`) to `/opt/run-deploy/minisign/`,
and you should be ready to go.

If you want you can test it.

```shell
test-template/deploy_remote.toml --ssh deploy@example.com --image-arg hostname=server_hostname
```

## CLI

### run-deploy-cli --help

```
usage: run-deploy-cli [-h] [--incus INCUS] [--image IMAGE] [--revision REVISION] command

Queries and operate run-deploy system

positional arguments:
  command              Commands: edition, last-deploy, last-deploy-blame, list-revision, revert, list-incus, list-image

options:
  -h, --help           show this help message and exit
  --incus INCUS        Required for: last-deploy, last-deploy-blame, list-revision, revert, list-image
  --image IMAGE        Required for: last-deploy, last-deploy-blame, list-revision, revert
  --revision REVISION  Required for: revert
```

### run-deploy-remote-cli deploy@example.com --help (`remote-incus`)

```
usage: run-deploy-cli [-h] [--incus INCUS] [--image IMAGE]
                      [--revision REVISION] [--cmd CMD]
                      command

Queries and operate run-deploy system

positional arguments:
  command              Commands: edition, exec, last-deploy, last-deploy-
                       blame, list-revision, revert, list-incus, list-image,
                       list-exec, permission-json

options:
  -h, --help           show this help message and exit
  --incus INCUS        Required for: exec, last-deploy, last-deploy-blame,
                       list-revision, revert, list-image, list-exec,
                       permission-json
  --image IMAGE        Required for: last-deploy, last-deploy-blame, list-
                       revision, revert, permission-json
  --revision REVISION  Required for: revert
  --cmd CMD            Required for: exec
```

### run-deploy-remote-cli deploy@example.com --help (`remote-metal`)

```
usage: run-deploy-cli [-h] [--image IMAGE] [--revision REVISION] [--cmd CMD]
                      command

Queries and operate run-deploy system

positional arguments:
  command              Commands: edition, exec, last-deploy, last-deploy-
                       blame, list-revision, revert, list-image, list-exec,
                       permission-json

options:
  -h, --help           show this help message and exit
  --image IMAGE        Required for: last-deploy, last-deploy-blame, list-
                       revision, revert, permission-json
  --revision REVISION  Required for: revert
  --cmd CMD            Required for: exec
```

### Note

`exec` execute a script located in `/opt/run-deploy/exec`, useful for executing oneshot
systemd unit.

## Permission

run-deploy has permission system disabled by default, to enable it you need to create the directory
`/opt/run-deploy/permission`
which will enable the permission system.

To add permission create the file `client_username@client_hostname.toml`
place it in `/opt/run-deploy/permission` with following content, edit as desired.

```toml
admin = false
banned = false
full-access = false
read-access = false

incus-full-access = false
incus-read-access = false

[metal]
full-acesss = false
# permit full access to image names
permit = ["image-name-1", "image-name-2"]
read-access = false
# permit read access to image names
permit-read = ["read-image-name-1", "read-image-name-2"]

[incus.container]
full-acesss = false
# permit full access to image names
permit = ["image-name-1", "image-name-2"]
read-access = false
# permit read access to image names
permit-read = ["read-image-name-1", "read-image-name-2"]
```

## Mounting images automatically at bootup

You need to edit `/etc/fstab`

### Outside the container
```
/opt/run-deploy/image/example/example.squashfs    /mnt/example      squashfs        loop    0 0
```

### Inside the container
You will need squashfuse for containers, as you can't use loop inside containers.

```
squashfuse#/opt/run-deploy/image/example/example.squashfs	 /mnt/example 	fuse	defaults,allow_other	0 0
```

### Mount the image manually
As root
```shell
mkdir /mnt/example
mount /mnt/example
```

### Note
The squashfs exec script will need to execute the script on the system that contains the following. I would place it in `/opt/run-deploy/script/deploy/example` (Replace example with image name)

```shell
#!/bin/dash
systemctl stop example
umount /mnt/example
mount /mmt/example || exit 1
systemctl start example
```

In quirk mode, the squashfs exec will also need to do a symlink swap. You will not need to do that in strict mode.
```
cd /opt/run-deploy/image/example
ln -sf example-2024-12-12.squashfs example.squashfs
/opt/run-deploy/script/deploy/example
```

Strict mode will write it own script and is the default, Quirk mode will let you write you own script that is stored in the image, not recommended as it will run the script in root.

To enable quirk mode delete `strict` file from `/opt/run-deploy/options` on server.