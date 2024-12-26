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

### For local machine

```shell
#!/bin/sh

# Create the image
image_location=$(./create_image.py)

# Deploy the image
run-deploy $image_location
# It will move the image to `/opt/run-deploy/image/{image_dir}`
```

### For remote machine

```shell
#!/bin/sh

# Create the image (on Local Machine)
image_location=$(./create_image.py)

# Sign the image (on Local Machine)
minisign -Sm $image_location

# Upload the image and signature
scp $image_location ${image_location}.minisig "deploy@example.com:/tmp/run-deploy"

# Deploy the image,
ssh deploy@example.com -- doas /opt/run-deploy/bin/run-deploy "/tmp/run-deploy/$(basename $image_location)" "$(whoami)@$(hostname)"

# "$(whoami)@$(hostname)" is used as public key and permission references.
```

## Image Manifest

The squashfs image must have a manifest at `_deploy/push.json` otherwise it will not deploy. The structure of the
manifest looks like the following.

```json
{
  "server_hostname": {
    "incus-name": "container_name",
    "image-dir": "example",
    "exec": "script_to_copy_and_exec"
  }
}
```

For `remote-metal` edition you can omit `incus-name`, but is required for
`remote-incus` and `local-incus` edition :)

You can have as many hostname as you want.

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
minisign -G -W
```

And upload the public key to `/opt/run-deploy/minisign/username@hostname.pub`, that the client username and hostname,
and you should be ready.

If you want you can test it.

```shell
test-template/deploy_remote.py server_hostname deploy@example.com
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
                       list-exec

options:
  -h, --help           show this help message and exit
  --incus INCUS        Required for: exec, last-deploy, last-deploy-blame,
                       list-revision, revert, list-image, list-exec
  --image IMAGE        Required for: last-deploy, last-deploy-blame, list-
                       revision, revert
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
                       blame, list-revision, revert, list-image, list-exec

options:
  -h, --help           show this help message and exit
  --image IMAGE        Required for: last-deploy, last-deploy-blame, list-
                       revision, revert
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
The squashfs exec script will need to execute the script on the system that contains the following. I would place it in `/opt/run-deploy/script/deploy/example`

```shell
#!/bin/dash
systemctl stop example
umount /mnt/example
mount /mmt/example || exit 1
systemctl start example
```

The squashfs exec will also need to do a symlink swap.
```
cd /opt/run-deploy/image/example
ln -sf example-2024-12-12.squashfs example.squashfs
/opt/run-deploy/script/deploy/example
```