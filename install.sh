#!/usr/bin/env bash

sudo cp bgrun bgrun.py /usr/local/bin
mkdir -p $HOME/.config/systemd/user/
cp bgrun.service $HOME/.config/systemd/user/

systemctl enable bgrun --user
systemctl start bgrun --user