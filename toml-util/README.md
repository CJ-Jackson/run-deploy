# run-deploy toml util

## run-deploy-image-toml.py

A little toml helper to automate image building

### create_image.toml
```toml
#!/usr/bin/env run-deploy-image-toml

# Image name (Mandatory)
name = "example"

# Temporary location (defaults to "/tmp"), can be omitted.
tmp_location = "/tmp"

# build script (Mandatory)
# It can be written in any language as long as it executable.
# Will pass `RUN_DEPLOY_PROJECT_PATH` environment variable
# for convenience
build_script = "./build.py"

# Manifest for `hostname-1`
[manifest.hostname-1]
# Incus container name (Mandatory for remote incus)
incus_name = "name_of_container"

# Manifest for `hostname-2` (Can be left empty)
[manifest.hostname-2]

# For allowing `--hostname` flag, useful for testing.
# Not recommended for production, will overwrite whole of manifest.
[manifest.__]

# It requires at least one manifest.
# The server must have a matching hostname, otherwise it won't deploy.
```

To execute
```shell
chmod 755 create_image.toml
./create_image.toml
```
Will return the name of the squashfs image.

### CLI

```
# ./create_image.toml --help
usage: run-deploy-image-toml [-h] [--hostname HOSTNAME] toml

Process TOML based image

positional arguments:
  toml

options:
  -h, --help           show this help message and exit
  --hostname HOSTNAME
```

## run-deploy-local-toml.py

A little toml helper to deploy image to local machines.

### deploy_local.toml
```toml
#!/usr/bin/env run-deploy-local-toml

# Pre script (optional)
# Loads before image creation script.
pre_script = ["./pre-script-1.sh", "./pre-script-1.sh"]

# Image creation script to execute (Mandatory)
create_image_script = "./create_image.toml"

# Used getting the last deploy revision and automatic emergency revert.
# Both are mandatory
incus = "name_of_incus_containers"
image = "example"
```

To execute
```shell
chmod 755 deploy_local.toml
./deploy_local.toml
```
Will deploy to local machine

### CLI
```
# ./deploy_local.toml --help
usage: run-deploy-local-toml [-h] [--image-arg IMAGE_ARG] toml

Process TOML based deploy

positional arguments:
  toml

options:
  -h, --help            show this help message and exit
  --image-arg IMAGE_ARG
```

## run-deploy-remote-toml.py
A little toml helper to deploy image to remote machines.

### deploy_remote.toml
```
#!/usr/bin/env run-deploy-remote-toml

# Pre script (optional)
# Loads before image creation script.
pre_script = ["./pre-script-1.sh", "./pre-script-1.sh"]

# Image creation script to execute (Mandatory)
create_image_script = "./create_image.toml"

# Image name (Mandatory)
image = "name_of_image"

# SSH Config, at least one is required
[ssh.'username@deploy.example-1.com']
# Mandatory for remote-incus
incus = "example-1"

# Can be left example, will still deploy to server.
[ssh.'username@deploy.example-2.com']

[ssh.'username@deploy.example-3.com']
# This is for remote-incus, for when it need to be deployed on host rather
# than container. (Optional)
metal = true

# To enable the `--ssh` flag
# Not recommended in production, only for testing.
[ssh.__]
incus = "test"

# To enable the `--ssh-metal` flag
# Not recommended in production, only for testing.
[ssh.__metal]
```

To execute
```shell
chmod 755 deploy_remote.toml
./deploy_remote.toml
```

### CLI
```
# ./deploy_remote.toml --help
usage: run-deploy-remote-toml [-h] [--image-arg IMAGE_ARG] [--ssh SSH] [--ssh-metal SSH_METAL] toml

Process TOML based deploy

positional arguments:
  toml

options:
  -h, --help            show this help message and exit
  --image-arg IMAGE_ARG
  --ssh SSH
  --ssh-metal SSH_METAL
```

## Template
### ./build.py (barebone)

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