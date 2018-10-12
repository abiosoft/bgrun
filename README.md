# bgrun

A simple tool to start a process in background and gets the pid.

## Usage

```sh
$ bgrun -l command.log -c "while sleep 1; do echo hello world; done"
1234

$ tail -f command.log
hello world
hello world
```

The process pid and log file can be used to monitor and terminate the process. bgrun does not manage the process after starting it.

## Install

* copy `bgrun` && `bgrun.py` to a directory in `$PATH`
* start daemon with `bgrun -s`

There is an helper install script that works for systemd based Linux.

```sh
git clone https://github.com/abiosoft/bgrun
cd bgrun && ./install.sh
```
