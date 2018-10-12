import subprocess
import argparse
import threading
import socket
import os
import json
import signal
import sys

BUFFER_SIZE = 1024
SOCKET_FILE = os.getenv(
    "BGRUN_SOCKET", "{}/.bgrun.sock".format(os.getenv("HOME")))


def process_args():
    parser = argparse.ArgumentParser(prog="bgrun")
    cgroup = parser.add_argument_group("client")
    cgroup.add_argument("-l", "--log-file",
                        help="file to direct command output to, otherwise output is discarded",
                        dest="log_file",
                        default=None,
                        )
    cgroup.add_argument("-c", "--command",
                        help="command or shell line to run. the command is passed to sh -c",
                        dest="command",
                        default=None,
                        )

    sgroup = parser.add_argument_group("server")
    sgroup.add_argument("-s", "--server",
                        help="start server",
                        dest="server",
                        action="store_true",
                        default=False,
                        )

    args = parser.parse_args()
    if args.server:
        server()
    elif args.command is not None:
        client(args.command, args.log_file)
    else:
        parser.print_usage()


def server():
    if os.path.exists(SOCKET_FILE):
        os.remove(SOCKET_FILE)

    register_interrupt_handler()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_FILE)
    server.listen()
    print("server listening on", SOCKET_FILE)
    while True:
        try:
            sock, _ = server.accept()
            msg = sock.recv(BUFFER_SIZE)
            resp = json.loads(msg)

            command = None
            log_file = None
            if "command" in resp:
                command = resp["command"]
            else:
                print("invalid request, command missing, discarding...")
                continue

            if "log_file" in resp:
                log_file = resp["log_file"]

            cmd = start(command=command, log_file=log_file)
            count = sock.send("{}".format(cmd.pid).encode())
            if count is 0:
                # failure, kill
                cmd.kill()
                continue

            thread = threading.Thread(target=wait, args=(cmd,))
            thread.run()
        except Exception as e:
            print("error occured", e, file=sys.stderr)


def client(command: str, log_file: str = None):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCKET_FILE)
    req = {"command": command, "log_file": log_file}
    count = client.send(json.dumps(req).encode())
    if count is 0:
        exit(1)

    pid = client.recv(BUFFER_SIZE)
    print(pid.decode())


def start(command: str, log_file: str = None):
    file = subprocess.DEVNULL
    if log_file is not None:
        file = open(file=log_file, mode='w+', )
    return subprocess.Popen(["sh", "-c", command], stdout=file, stderr=file)


def wait(cmd: subprocess.Popen):
    cmd.wait()
    if cmd.returncode is not 0:
        print("command '{}' exits with error code {}".format(
            " ".join(cmd.args), cmd.returncode))


def register_interrupt_handler():
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def handler(sig, frame):
    os.remove(SOCKET_FILE)
    print("terminating... received", sig)
    exit(0)


process_args()
