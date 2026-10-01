#!/usr/bin/env python3
"""Small production supervisor for the bot and Hermes gateway processes."""

from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass
class Service:
    name: str
    command: tuple[str, ...]
    process: subprocess.Popen | None = None
    failures: int = 0
    restart_at: float = 0.0


class HermesSupervisor:
    """Restart services independently and stop each complete process group."""

    def __init__(
        self,
        services: Sequence[tuple[str, Sequence[str]]],
        *,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        killpg: Callable[[int, int], None] = os.killpg,
        poll_interval: float = 0.5,
        backoff_initial: float = 1.0,
        backoff_max: float = 60.0,
        shutdown_grace: float = 20.0,
    ) -> None:
        self.services = [
            Service(name=name, command=tuple(command))
            for name, command in services
        ]
        self._popen = popen
        self._clock = clock
        self._sleep = sleeper
        self._killpg = killpg
        self.poll_interval = poll_interval
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.shutdown_grace = shutdown_grace
        self._stop_event = threading.Event()

    def request_stop(self, _signum: int | None = None, _frame: object = None) -> None:
        self._stop_event.set()

    def _schedule_restart(self, service: Service, now: float) -> float:
        service.failures += 1
        delay = min(
            self.backoff_initial * (2 ** (service.failures - 1)),
            self.backoff_max,
        )
        service.restart_at = now + delay
        return delay

    def _signal_group(self, process: subprocess.Popen, sig: int) -> None:
        try:
            if os.name == "posix":
                self._killpg(process.pid, sig)
            else:
                process.send_signal(sig)
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def tick(self, now: float | None = None) -> None:
        """Perform one poll/start pass; exposed for deterministic fake-process tests."""
        now = self._clock() if now is None else now
        for service in self.services:
            process = service.process
            if process is not None:
                status = process.poll()
                if status is None:
                    continue
                self._signal_group(process, signal.SIGTERM)
                service.process = None
                delay = self._schedule_restart(service, now)
                print(
                    f"[supervisor] {service.name} exited ({status}); "
                    f"restart in {delay:.1f}s",
                    file=sys.stderr,
                    flush=True,
                )

            if service.process is None and now >= service.restart_at:
                try:
                    service.process = self._popen(
                        list(service.command),
                        start_new_session=True,
                    )
                except OSError as exc:
                    delay = self._schedule_restart(service, now)
                    print(
                        f"[supervisor] could not start {service.name} ({exc}); "
                        f"retry in {delay:.1f}s",
                        file=sys.stderr,
                        flush=True,
                    )

    def _wait_for_exit(self, process: subprocess.Popen, deadline: float) -> bool:
        while process.poll() is None and self._clock() < deadline:
            remaining = max(0.0, deadline - self._clock())
            self._sleep(min(self.poll_interval, remaining))
        return process.poll() is not None

    def stop_all(self) -> None:
        active = [
            service.process
            for service in self.services
            if service.process is not None
        ]
        for process in active:
            self._signal_group(process, signal.SIGTERM)

        deadline = self._clock() + self.shutdown_grace
        for process in active:
            if not self._wait_for_exit(process, deadline):
                self._signal_group(process, signal.SIGKILL)
                try:
                    process.wait(timeout=max(1.0, self.poll_interval * 2))
                except (subprocess.TimeoutExpired, OSError):
                    pass
        for service in self.services:
            service.process = None

    def run(self) -> None:
        try:
            while not self._stop_event.is_set():
                self.tick()
                self._stop_event.wait(self.poll_interval)
        finally:
            self.stop_all()


def production_services(root: Path) -> list[tuple[str, tuple[str, ...]]]:
    return [
        ("bot", ("bash", str(root / "scripts" / "run-bot.sh"))),
        ("hermes", ("bash", str(root / "scripts" / "run-hermes.sh"))),
    ]


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    supervisor = HermesSupervisor(production_services(root))
    previous_handlers: dict[int, object] = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, supervisor.request_stop)
    try:
        supervisor.run()
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())