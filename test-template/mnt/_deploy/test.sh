#!/bin/dash
umount /mnt/test
mount /mnt/test || exit 1
echo "success"