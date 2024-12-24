# run-deploy

'run-deploy' is a stateless deployment solution that is quite simple, elegant and fun to use.  It relies on the following sane open-soruce solution.

* [SquashFS](https://en.wikipedia.org/wiki/SquashFS)
  * With the json manifest located inside the image `_deploy/push.json`
  * **FUN FACT**: It was introduct in 2002, while [Jenkins](https://en.wikipedia.org/wiki/Jenkins_(software)) was introduce in 2011... Amazing.
* [OpenDOAS](https://wiki.archlinux.org/title/Doas)
  * To allow deploy user to run the script as root, it is a lot safer than SUDO and Polkit.
* [Minisign](https://jedisct1.github.io/minisign/)
  * For image and user verification, the public key is cherry picked by the client `username@hostname`, as mentioned earlier it a stateless system.
  * The image itself has to be signed by a private key.
  * It is a lightweight compared to GnuPG.
  * The public key goes into `/opt/run-deploy/minisign/username@hostname.pub`

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