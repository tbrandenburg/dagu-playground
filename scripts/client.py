"""Small, bounded client for the pinned Dagu REST API; no third-party packages."""

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Callable, TypedDict, TypeVar, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
T = TypeVar("T")


class Node(TypedDict):
    step: dict[str, str]
    statusLabel: str
    retryCount: int
    startedAt: str
    finishedAt: str


class Run(TypedDict):
    name: str
    dagRunId: str
    workerId: str
    statusLabel: str
    nodes: list[Node]


class Worker(TypedDict):
    id: str
    healthStatus: str
    totalPollers: int
    labels: dict[str, str]


class ApiError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


def require(condition: object, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def wait(check: Callable[[], T], description: str, timeout: float = 90) -> T:
    deadline = time.monotonic() + timeout
    while True:
        result = check()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting for {description}")
        time.sleep(0.5)


def compose(*arguments: str) -> str:
    return subprocess.run(
        ["docker", "compose", *arguments],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        timeout=180,
    ).stdout.strip()


def replicas() -> list[str]:
    return compose("ps", "-q", "worker").splitlines()


def container(identifier: str, *arguments: str) -> str:
    return subprocess.run(
        ["docker", "exec", identifier, *arguments],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        timeout=15,
    ).stdout.strip()


class Client:
    def __init__(self, base: str | None = None) -> None:
        self.base = base or f"http://127.0.0.1:{os.environ.get('PORT', '8100')}"

    def request(
        self, path: str, body: dict[str, object] | None = None
    ) -> dict[str, object]:
        data = None if body is None else json.dumps(body).encode()
        request = Request(
            f"{self.base}/api/v1/{path}",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=10) as response:
                result = json.load(response)
        except HTTPError as error:
            raise ApiError(error.code, error.read().decode()) from error
        except (URLError, TimeoutError) as error:
            raise ConnectionError(f"Cannot reach {self.base}: {error}") from error
        require(isinstance(result, dict), "API response must be a JSON object")
        return cast(dict[str, object], result)

    def workers(self) -> list[Worker]:
        result = self.request("workers")
        require(not result.get("errors"), f"Worker API errors: {result.get('errors')}")
        return [
            worker
            for worker in cast(list[Worker], result["workers"])
            if worker["healthStatus"] == "healthy"
        ]

    def ready(self, count: int) -> list[Worker]:
        require(count > 0, "No running workers; run make up")
        return wait(
            lambda: workers if len(workers := self.workers()) == count else [],
            f"{count} healthy workers",
        )

    def start(self, name: str, hold: int = 3) -> str:
        body: dict[str, object] = (
            {"params": json.dumps({"HOLD": str(hold)})}
            if name == "hello-worker"
            else {}
        )
        return str(self.request(f"dags/{name}/start", body)["dagRunId"])

    def run(self, name: str, identifier: str) -> Run:
        return cast(Run, self.request(f"dags/{name}/dag-runs/{identifier}")["dagRun"])

    def finished(self, name: str, identifier: str, expected: str = "succeeded") -> Run:
        def terminal() -> Run | None:
            try:
                run = self.run(name, identifier)
            except ApiError as error:
                if error.status == 404:
                    return None
                raise
            if run["statusLabel"] in {"queued", "running", "not_started"}:
                return None
            require(run["statusLabel"] == expected, f"Unexpected run result: {run}")
            return run

        return cast(Run, wait(terminal, f"{name}/{identifier}: {expected}"))

    def log(self, run: Run, step: str, stream: str = "stdout") -> str:
        return str(
            self.request(
                f"dag-runs/{run['name']}/{run['dagRunId']}/steps/{step}/log"
                f"?stream={stream}"
            )["content"]
        )
