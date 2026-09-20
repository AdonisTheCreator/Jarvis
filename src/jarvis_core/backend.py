"""The backend adapter contract (docs/05 §6.2).

Every agent runtime, control plane and service reaches the core through this
interface. Two differences from the sketch in the blueprint, both learned the
hard way:

* ``execute`` takes an **idempotency key**. Without it, retries at more than
  one layer duplicate side effects.
* ``estimate`` must be **cheap** -- a registry lookup and arithmetic, never a
  model call. It runs on every routing decision, and a model call there is
  where latency stacking begins.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Iterator, Mapping, Sequence


class TaskState(StrEnum):
    """Adapters must honour what each terminal state promises about the *effect*,
    because the idempotency ledger acts on it.

    ``FAILED`` is the only state that asserts the side effect **did not
    happen**; it is the only one that frees the claim for a retry. If an
    adapter cannot promise that -- a send the provider may already have
    accepted, a cancellation that raced -- it must report ``CANCELLED`` or
    ``INTERRUPTED``, which hold the claim instead.
    """

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SUCCEEDED = "succeeded"
    """Completed. The effect happened."""
    FAILED = "failed"
    """Completed unsuccessfully, and the effect **provably did not happen**."""
    CANCELLED = "cancelled"
    """Stopped, but the effect may already have landed."""
    INTERRUPTED = "interrupted"
    """Stopped mid-flight; the effect may have partly landed."""

    @property
    def terminal(self) -> bool:
        return self in {
            TaskState.SUCCEEDED, TaskState.FAILED,
            TaskState.CANCELLED, TaskState.INTERRUPTED,
        }

    @property
    def guarantees_no_effect(self) -> bool:
        """True only where an adapter has promised nothing happened."""
        return self is TaskState.FAILED


@dataclass(frozen=True, slots=True)
class Task:
    """One unit of work handed to a backend."""

    capability: str
    target: str
    params: Mapping[str, Any] = field(default_factory=dict)
    session: str = "default"
    subject_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Estimate:
    """What this backend expects the task to cost.

    Must be computable without a model call.
    """

    cost_usd: float
    latency_ms: float
    confidence: float
    """Historical success rate for this capability on this backend -- measured,
    not asserted. A backend with no history reports low confidence rather than
    optimism."""


@dataclass(frozen=True, slots=True)
class HealthStatus:
    healthy: bool
    detail: str = ""
    checked_at: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class TaskHandle:
    id: str
    backend_id: str
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class TaskStatus:
    handle: TaskHandle
    state: TaskState
    detail: str = ""
    result_ref: str | None = None


class NotSupported(Exception):
    """A backend does not implement an optional operation.

    Raised by ``compensate`` when no undo exists -- which must be *declared*,
    not discovered, because it drives the approval tier.
    """


class AgentBackend(ABC):
    """What every adapter implements.

    Adapters translate; they do not decide. Routing, policy and memory stay in
    the core, so swapping a control plane costs an adapter rather than a
    rewrite.
    """

    @property
    @abstractmethod
    def id(self) -> str: ...

    @property
    @abstractmethod
    def capabilities(self) -> Sequence[str]:
        """Capability names this backend can serve."""

    @abstractmethod
    def health(self) -> HealthStatus: ...

    @abstractmethod
    def estimate(self, task: Task) -> Estimate:
        """Cheap. No model call, no network round trip on the hot path."""

    @abstractmethod
    def execute(self, task: Task, idempotency_key: str | None = None) -> TaskHandle: ...

    @abstractmethod
    def status(self, handle: TaskHandle) -> TaskStatus: ...

    def stream(self, handle: TaskHandle) -> Iterator[Mapping[str, Any]]:
        """Live events. Default: nothing to stream."""
        return iter(())

    def interrupt(self, handle: TaskHandle, instruction: str | None = None) -> TaskStatus:
        """Stop or redirect a running task. This is the barge-in target."""
        raise NotSupported(f"{self.id} cannot interrupt tasks")

    def cancel(self, handle: TaskHandle) -> TaskStatus:
        raise NotSupported(f"{self.id} cannot cancel tasks")

    def resume(self, handle: TaskHandle) -> TaskStatus:
        raise NotSupported(f"{self.id} cannot resume tasks")

    def compensate(self, handle: TaskHandle) -> TaskStatus:
        """Undo a completed task, where an undo exists.

        Raising :class:`NotSupported` is a valid and important answer: "no
        undo" is a machine-readable property that raises the approval tier.
        """
        raise NotSupported(f"{self.id} declares no compensating action")
