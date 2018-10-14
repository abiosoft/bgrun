# bgrun

A simple tool to start a process in background and get the pid.

## Usage

```txt
$ bgrun -l ping.log ping 1.1.1.1
1234

$ tail -f ping.log
64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=11.1 ms
64 bytes from 1.1.1.1: icmp_seq=2 ttl=57 time=12.4 ms
```

The process pid and log file can be used to monitor and terminate the process.

### List running commands

```txt
bgrun -r
[{"pid": 1234, "command": "ping 1.1.1.1", "log_file": "ping.log"}]
```

### Help

For full usage

```txt
$ bgrun -h

usage: bgrun [-h] [-l LOG_FILE] [-r] [-d] [-i] [-f] [command] ...

optional arguments:
  -h, --help            show this help message and exit

client:
  -l LOG_FILE, --log-file LOG_FILE
                        file to direct command output to, otherwise output is
                        discarded.
  command               command to run.
  args                  arguments to pass to command.
  -r, --running         list running commands, the output is json format.

daemon:
  -d, --daemon          start daemon.
  -i, --ignore          ignore running commands when daemon exits. By default,
                        bgrun terminates all running commands on exit.
  -f, --force           forcefully start even if the socket file exists. This
                        can be as a result of another bgrun daemon running, or
                        a previously running daemon did not terminate
                        gracefully.

```

## Install

* copy `bgrun` && `bgrun.py` to a directory in `$PATH`
* start daemon with `bgrun --daemon`

There is an helper install script that works for systemd based Linux.

```sh
git clone https://github.com/abiosoft/bgrun
cd bgrun && ./install.sh
```
