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
                        help="file to direct command output to, otherwise output is discarded.",
                        dest="log_file",
                        default=None,
                        )
    cgroup.add_argument("command",
                        help="command to run.",
                        nargs='?',
                        )
    cgroup.add_argument("args",
                        help="arguments to pass to command.",
                        nargs=argparse.REMAINDER,
                        )
    cgroup.add_argument("-r", "--running",
                        help="list running commands, the output is json format.",
                        dest="running",
                        action="store_true",
                        default=False,
                        )
    sgroup = parser.add_argument_group("daemon")
    sgroup.add_argument("-d", "--daemon",
                        help="start daemon.",
                        dest="daemon",
                        action="store_true",
                        default=False,
                        )
    sgroup.add_argument("-i", "--ignore",
                        help="ignore running commands when daemon exits. By default, bgrun terminates all running commands on exit.",
                        dest="ignore",
                        action="store_true",
                        default=False,
                        )
    sgroup.add_argument("-f", "--force",
                        help="forcefully start even if the socket file exists. This can be as a result of another bgrun daemon running, or a previously running daemon did not terminate gracefully.",
                        dest="force",
                        action="store_true",
                        default=False,
                        )

    args = parser.parse_args()
    if args.daemon:
        Daemon(args.ignore, args.force).listen()
    elif args.running:
        Client().running()
    elif args.command is not None:
        Client().run(args.command, args.args, args.log_file)
    else:
        parser.print_usage()


class Client:

    def run(self, command: str, args: list, log_file: str = None):
        req = {
            "type": "command",
            "command": command,
            'args': args,
            "log_file": log_file,
        }
        resp = self.send(req)
        if resp is None:
            exit(1)
        print(resp)

    def running(self):
        req = {"type": "running"}
        resp = self.send(req)
        if resp is None:
            exit(1)
        print(resp)

    def send(self, message: dict):
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(SOCKET_FILE)
            count = client.send(json.dumps(message).encode())
            if count is 0:
                # failure
                return None
        except FileNotFoundError:
            print("connection to socket file failed, is the daemon running?")
            return None

        return client.recv(BUFFER_SIZE).decode()


class Daemon:
    def __init__(self, ignore: bool = False, force: bool = False):
        self.ignore_running = ignore
        self.force_start = force
        self.commands = {}
        self.mutex = threading.Lock()

    def listen(self):
        self._connect()
        self._listen()

    def _connect(self):
        if os.path.exists(SOCKET_FILE):
            if self.force_start:
                os.remove(SOCKET_FILE)
            else:
                print("socket file in use, is another daemon running? Start bgrun with -f to forcefully start the deamon.", file=sys.stderr)
                exit(1)
        self.daemon = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.daemon.bind(SOCKET_FILE)

    def _listen(self):
        self._interrupt_handlers()

        self.daemon.listen()
        print("daemon listening on", SOCKET_FILE)
        while True:
            try:
                self._accept()
            except Exception as e:
                print("error occured", e, file=sys.stderr)
                pass

    def _accept(self):
        conn, _ = self.daemon.accept()
        msg = conn.recv(BUFFER_SIZE)
        req = json.loads(msg.decode())
        if "type" not in req:
            conn.close()
            return

        if req["type"] == "running":
            self.running_commands(conn)
        elif req["type"] == "command":
            if "command" not in req:
                print("missing command, discarding...")
                conn.close()
                return

            command = req["command"]
            log_file = None
            args = []
            if "log_file" in req:
                log_file = req["log_file"]
            if "args" in req and type(req["args"]) is list:
                args = req["args"]

            thread = threading.Thread(
                target=self.run, args=(conn, command, args, log_file,))
            thread.start()
        else:
            print("invalid request, discarding...")
            conn.close()

    def run(self, conn: socket.socket, command: str, args: list, log_file: str = None):
        cmd = self.start(command, args, log_file)

        desc = " ".join([command] + args)
        print("started", desc, "pid", cmd.pid)

        count = conn.send("{}".format(cmd.pid).encode())
        if count is 0:
            # failure, kill
            cmd.kill()
        conn.close()

        self.wait(cmd, log_file)
        print("done with", desc, "pid", cmd.pid)

    def start(self, command: str, args: list, log_file: str = None) -> subprocess.Popen:
        file = subprocess.DEVNULL
        if log_file is not None:
            file = open(file=log_file, mode='w+', )
        return subprocess.Popen([command] + args, stdout=file, stderr=file)

    def wait(self, cmd: subprocess.Popen, log_file: str = None):
        # add command to list
        self.mutex.acquire()
        self.commands[cmd.pid] = {
            "cmd": cmd,
            "log_file": log_file,
        }
        self.mutex.release()

        cmd.wait()
        if cmd.returncode is not 0:
            print("command '{}' exits with error code {}".format(
                " ".join(cmd.args), cmd.returncode))

        # remove command from list
        self.mutex.acquire()
        self.commands.pop(cmd.pid, None)
        self.mutex.release()

    def running_commands(self, conn: socket.socket):
        resp = []
        for pid in self.commands:
            args = self.commands[pid]["cmd"].args
            log_file = self.commands[pid]["log_file"]
            resp.append({
                "pid": pid,
                "command": " ".join(args),
                "log_file": log_file,
            })

        conn.send(json.dumps(resp).encode())
        conn.close()

    def _interrupt_handlers(self):
        signal.signal(signal.SIGINT, self.handler)
        signal.signal(signal.SIGTERM, self.handler)

    def handler(self, sig, frame):
        print("terminating... received", sig)
        try:
            os.remove(SOCKET_FILE)
        except Exception as e:
            print("unexpected error", e, file=sys.stderr)


        # terminate all running commands
        try:
            if not self.ignore_running:
                for _, cmd in self.commands:
                    cmd["cmd"].kill()
        finally:
            exit(0)

process_args()
