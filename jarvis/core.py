"""Vendor-independent, in-memory lifecycle; not the production Record or sandbox.

Only trusted simulated workers may be attached in this milestone. Cancellation
acknowledgement is explicit: stopping an await is not proof that a worker stopped.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol
from uuid import uuid4


class Status(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"  # worker may still be running; never retry automatically


TERMINAL = {Status.CANCELLED, Status.SUCCEEDED, Status.FAILED, Status.UNKNOWN}


@dataclass(frozen=True)
class Request:
    project: str
    instruction: str

    def __post_init__(self) -> None:
        if not self.project.strip() or not self.instruction.strip():
            raise ValueError("project and instruction must be nonempty")


@dataclass(frozen=True)
class Result:
    success: bool
    summary: str
    artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class Event:
    sequence: int
    task_id: str
    kind: str
    stage: str | None = None


class Worker(Protocol):
    """Each adapter owns its external session and enforces its task scope.

    run() returns only when work has stopped. cancel() must be idempotent and
    return True only after ALL owned work has stopped, including descendants.
    IDs are reserved before run() begins so cancellation can race with launch.
    Inputs/results are handoff data, never elevated instructions or approvals.
    """

    async def run(self, task_id: str, request: Request, prior: Result | None) -> Result: ...

    async def cancel(self, task_id: str) -> bool: ...


@dataclass(frozen=True)
class Stage:
    name: str
    worker: Worker


@dataclass
class _Task:
    request: Request
    status: Status = Status.QUEUED
    active: Stage | None = None
    result: Result | None = None
    runner: asyncio.Task | None = None
    stop_requested: bool = False
    cancel_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class Coordinator:
    """Single-event-loop coordinator with process-local duplicate suppression.

    No restart recovery or durable idempotency. UNKNOWN blocks new submissions
    until this coordinator is discarded after the worker is externally reconciled.
    """

    def __init__(self, stages: tuple[Stage, ...], cancel_timeout: float = 1.0):
        if not stages or len({s.name for s in stages}) != len(stages):
            raise ValueError("provide stages with unique names")
        if cancel_timeout <= 0:
            raise ValueError("cancel_timeout must be positive")
        self._stages = stages
        self._cancel_timeout = cancel_timeout
        self._tasks: dict[str, _Task] = {}
        self._keys: dict[str, str] = {}
        self._events: list[Event] = []

    def _emit(self, task_id: str, kind: str, stage: str | None = None) -> None:
        # Metadata only: no prompts, provider output, credentials or personal data.
        self._events.append(Event(len(self._events) + 1, task_id, kind, stage))

    def events(self, task_id: str) -> tuple[Event, ...]:
        self._tasks[task_id]  # reject unknown IDs
        return tuple(e for e in self._events if e.task_id == task_id)

    def submit(self, request: Request, idempotency_key: str) -> str:
        if not idempotency_key.strip():
            raise ValueError("idempotency key must be nonempty")
        if idempotency_key in self._keys:
            task_id = self._keys[idempotency_key]
            if self._tasks[task_id].request != request:
                raise ValueError("idempotency key already belongs to a different request")
            return task_id
        if any(t.status == Status.UNKNOWN for t in self._tasks.values()):
            raise RuntimeError("unreconciled worker; new work is blocked")
        task_id = str(uuid4())
        task = _Task(request)
        self._tasks[task_id] = task
        self._keys[idempotency_key] = task_id
        self._emit(task_id, Status.QUEUED.value)
        task.runner = asyncio.create_task(self._run(task_id))
        return task_id

    def status(self, task_id: str) -> Status:
        return self._tasks[task_id].status

    async def wait(self, task_id: str) -> Status:
        task = self._tasks[task_id]
        if task.runner:
            # A caller timing out must not silently cancel delegated work.
            try:
                await asyncio.shield(task.runner)
            except asyncio.CancelledError:
                if not task.runner.cancelled():
                    raise
        return task.status

    def result(self, task_id: str) -> Result | None:
        return self._tasks[task_id].result

    async def _run(self, task_id: str) -> None:
        task = self._tasks[task_id]
        if task.stop_requested:
            return
        task.status = Status.RUNNING
        self._emit(task_id, task.status.value)
        prior = None
        try:
            for stage in self._stages:
                if task.stop_requested:
                    return
                task.active = stage
                self._emit(task_id, "stage_started", stage.name)
                prior = await stage.worker.run(task_id, task.request, prior)
                if task.stop_requested:
                    return
                task.active = None
                task.result = prior
                self._emit(task_id, "stage_completed", stage.name)
                if not prior.success:
                    task.status = Status.FAILED
                    self._emit(task_id, task.status.value)
                    return
            task.status = Status.SUCCEEDED
            self._emit(task_id, task.status.value)
        except asyncio.CancelledError:
            if not task.stop_requested:
                task.status = Status.UNKNOWN
                self._emit(task_id, task.status.value)
        except Exception:
            # Transport exceptions do not prove that external execution stopped.
            if not task.stop_requested:
                task.status = Status.UNKNOWN
                self._emit(task_id, task.status.value)

    async def cancel(self, task_id: str) -> Status:
        task = self._tasks[task_id]
        async with task.cancel_lock:
            if task.status in TERMINAL:
                return task.status
            task.stop_requested = True
            task.status = Status.CANCELLING
            self._emit(task_id, task.status.value)
            confirmed = task.active is None
            if task.active:
                try:
                    confirmed = await asyncio.wait_for(
                        task.active.worker.cancel(task_id), self._cancel_timeout
                    )
                except (Exception, asyncio.CancelledError):
                    confirmed = False
            task.status = Status.CANCELLED if confirmed else Status.UNKNOWN
            self._emit(task_id, task.status.value)
            # Clean up local waiting only after recording external stop certainty.
            if task.runner and not task.runner.done():
                task.runner.cancel()
                await asyncio.gather(task.runner, return_exceptions=True)
            return task.status
