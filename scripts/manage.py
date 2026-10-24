"""Validate lifecycle arguments before changing Compose state."""

import argparse
import os
import socket

from scripts.client import Client, compose, replicas


def integer(value: str, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Expected an integer") from error
    if not minimum <= number <= maximum:
        raise argparse.ArgumentTypeError(f"Expected {minimum}..{maximum}")
    return number


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["up", "scale", "ready"])
    parser.add_argument("--workers", type=lambda value: integer(value, 1, 5), default=2)
    parser.add_argument(
        "--port",
        type=lambda value: integer(value, 1024, 65535),
        default=os.environ.get("PORT", "8100"),
    )
    args = parser.parse_args()
    os.environ["PORT"] = str(args.port)
    if args.action != "ready":
        if not compose("ps", "-q", "dagu"):
            with socket.socket() as sock:
                try:
                    sock.bind(("127.0.0.1", args.port))
                except OSError as error:
                    parser.error(
                        f"Port {args.port} is occupied; use make up PORT=<free-port>: {error}"
                    )
        compose(
            "up",
            "-d",
            "--scale",
            f"worker={args.workers}",
            "--wait",
            "--wait-timeout",
            "120",
        )
    workers = Client().ready(
        args.workers if args.action != "ready" else len(replicas())
    )
    print(f"Ready: http://127.0.0.1:{args.port} with {len(workers)} healthy workers")


if __name__ == "__main__":
    main()
