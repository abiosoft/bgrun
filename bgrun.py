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


commands = {}
mutex = threading.Lock()


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
    cgroup.add_argument("-r", "--running",
                        help="list running commands, the output is json format",
                        dest="running",
                        action="store_true",
                        default=False,
                        )
    sgroup = parser.add_argument_group("daemon")
    sgroup.add_argument("-d", "--daemon",
                        help="start daemon",
                        dest="daemon",
                        action="store_true",
                        default=False,
                        )

    args = parser.parse_args()
    if args.daemon:
        daemon()
    elif args.running:
        running()
    elif args.command is not None:
        command(args.command, args.log_file)
    else:
        parser.print_usage()


def daemon():
    if os.path.exists(SOCKET_FILE):
        os.remove(SOCKET_FILE)

    register_interrupt_handler()

    daemon = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    daemon.bind(SOCKET_FILE)
    daemon.listen()
    print("daemon listening on", SOCKET_FILE)
    while True:
        try:
            conn, _ = daemon.accept()
            msg = conn.recv(BUFFER_SIZE)
            req = json.loads(msg.decode())
            if "type" not in req :
                conn.close()
                continue

            if req["type"] == "running":
                running_commands(conn)
            elif req["type"] == "command":
                if "command" not in req:
                    print("missing command, discarding...")
                    conn.close()
                    continue

                command = req["command"]
                log_file = None
                if "log_file" in req:
                    log_file = req["log_file"]

                thread = threading.Thread(
                    target=run, args=(conn, command, log_file,))
                thread.start()
            else:
                print("invalid request, discarding...")
                conn.close()

        except Exception as e:
            print("error occured", e, file=sys.stderr)


def command(command: str, log_file: str = None):
    req = {"type": "command", "command": command, "log_file": log_file}
    resp = client_message(req)
    print(resp)


def running():
    req = {"type": "running"}
    resp = client_message(req)
    print(resp)


def client_message(message: dict):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCKET_FILE)
    count = client.send(json.dumps(message).encode())
    if count is 0:
        # failure
        return None

    return client.recv(BUFFER_SIZE).decode()


def run(conn: socket.socket, command: str, log_file: str = None):
    cmd = start(command=command, log_file=log_file)
    print("started", command, "pid", cmd.pid)

    count = conn.send("{}".format(cmd.pid).encode())
    if count is 0:
        # failure, kill
        cmd.kill()
    conn.close()
    
    wait(cmd, log_file)
    print("done with", command, "pid", cmd.pid)


def start(command: str, log_file: str = None) -> subprocess.Popen:
    file = subprocess.DEVNULL
    if log_file is not None:
        file = open(file=log_file, mode='w+', )
    return subprocess.Popen(["sh", "-c", command], stdout=file, stderr=file)


def wait(cmd: subprocess.Popen, log_file: str = None):
    # add command to list
    mutex.acquire()
    commands[cmd.pid] = {
        "cmd": cmd,
        "log_file": log_file,
    }
    mutex.release()

    cmd.wait()
    if cmd.returncode is not 0:
        print("command '{}' exits with error code {}".format(
            " ".join(cmd.args), cmd.returncode))

    # remove command from list
    mutex.acquire()
    commands.pop(cmd.pid, None)
    mutex.release()


def running_commands(conn: socket.socket):
    resp = []
    for pid in commands:
        args = commands[pid]["cmd"].args
        log_file = commands[pid]["log_file"]
        resp.append({
            "pid": pid,
            "command": " ".join(args),
            "log_file": log_file,
        })

    conn.send(json.dumps(resp).encode())
    conn.close()


def register_interrupt_handler():
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def handler(sig, frame):
    os.remove(SOCKET_FILE)
    print("terminating... received", sig)

    # terminate all running commands
    try:
        for _, cmd in commands:
            cmd["cmd"].kill()
    finally:
        exit(0)


process_args()
