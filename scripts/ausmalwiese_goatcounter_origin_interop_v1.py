#!/usr/bin/env python3
"""Run the pinned coloring-pages Nginx proof against the actual collector.

CI-only synthetic harness: substitutes only catalog input and backend transport.
The real peer admission, bounded workers and HTTP parser handle every request.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import socket
import struct
import sys
import threading
import time

import ausmalwiese_goatcounter_origin_v1 as origin


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, type=Path)
    args = parser.parse_args()
    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "github-hosted":
        raise RuntimeError("EPHEMERAL_GITHUB_RUNNER_REQUIRED")
    expected = Path(os.environ["GITHUB_WORKSPACE"]) / ".transport-fixture"
    if args.fixture.resolve() != expected.resolve():
        raise RuntimeError("FIXTURE_PATH")
    sys.path.insert(0, str(args.fixture / "tools"))
    spec = importlib.util.spec_from_file_location(
        "transport", args.fixture / "tools/goatcounter_origin_isolated_probe.py")
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)

    class ActualReceiver:
        def __init__(self, path):
            self.path = path
            self.records, self.backend = [], []
            self.lock = threading.Lock()
            self.mode = "ok"
            self.listener = None

        def start(self):
            owner = self

            class Capture:
                def __init__(self, conn):
                    self.conn, self.raw, self.recorded = conn, b"", False

                def settimeout(self, value):
                    self.conn.settimeout(value)

                def recv(self, size):
                    data = self.conn.recv(size)
                    self.raw += data
                    if not self.recorded and b"\r\n\r\n" in self.raw:
                        head, body = self.raw.split(b"\r\n\r\n", 1)
                        if len(body) == 21:
                            self.recorded = True
                            lines = head.decode("ascii").split("\r\n")
                            method, target, _ = lines[0].split(" ")
                            headers = [tuple(p.strip() for p in line.split(":", 1)) for line in lines[1:]]
                            _, uid, _ = struct.unpack("iII", self.conn.getsockopt(
                                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("iII")))
                            with owner.lock:
                                owner.records.append((method, target, headers, body, uid))
                    return data

                def sendall(self, data):
                    if owner.mode == "malformed":
                        data = b"invalid upstream response\r\n"
                    self.conn.sendall(data)

                def close(self):
                    self.conn.close()

            class ObservedCollector(origin.Collector):
                def handle(self, conn):
                    super().handle(Capture(conn))

            class SyntheticCatalog:
                def get(self):
                    return origin.visible_ids(transport.CATALOG)

            def synthetic_backend(page_id):
                with owner.lock:
                    owner.backend.append(origin.payload(page_id))
                    mode = owner.mode
                if mode == "slow":
                    time.sleep(1)

            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind(str(self.path))
            self.listener.listen(8)
            os.chmod(self.path, 0o660)
            self.collector = ObservedCollector(self.listener, (101, 101), SyntheticCatalog(), synthetic_backend)
            self.thread = threading.Thread(target=self.collector.serve)
            self.thread.start()

        def stop(self):
            if self.listener:
                self.collector.stop.set()
                self.thread.join(timeout=1)
                self.listener.close()
                self.listener = None
                self.path.unlink()

        def counts(self):
            with self.lock:
                return len(self.records), len(self.backend)

    transport.Receiver = ActualReceiver
    transport.probe()
    print("GOATCOUNTER_ORIGIN_INTEROP=PASS ACTUAL_COLLECTOR=TRUE LIVE=FALSE")


if __name__ == "__main__":
    main()
