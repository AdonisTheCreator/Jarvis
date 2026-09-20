"""Jarvis Core.

The small, permanent layer: identity, capability routing, policy, canonical
memory, the Record, and the decision layer.

Design invariant (docs/05 §1): **no module in this package may import a vendor
type.** Control planes, agent runtimes and model providers live behind
adapters. ``tests/test_invariants.py`` asserts this rather than trusting it.
"""
from .autonomy import AutonomyClass
from .backend import AgentBackend, Estimate, HealthStatus, Task, TaskHandle, TaskState
from .capability import (
    Capability, CapabilityRegistry, ModelCabinet, ModelPosition, PositionPolicy, PrivacyClass,
)
from .errors import (
    ApprovalInvalid, ApprovalRequired, JarvisCoreError, KillSwitchEngaged,
    PolicyDenied, RecordIntegrityError, SubjectForgotten,
)
from .idempotency import ClaimToken, IdempotencyLedger, derive_key
from .killswitch import FileKillSwitch, KillSwitch, NullKillSwitch
from .memory import CanonicalMemory, Fact, MemoryClass, Provenance
from .quarantine import EvidenceRef, Proposal, QuarantinedWorker
from .router import (
    CapabilityRouter, ClaimOutcome, DuplicateSuppressed, NoBackendAvailable, TaskMismatch,
)

__all__ = [
    "AutonomyClass",
    "AgentBackend", "Estimate", "HealthStatus", "Task", "TaskHandle", "TaskState",
    "Capability", "CapabilityRegistry", "ModelCabinet", "ModelPosition",
    "PositionPolicy", "PrivacyClass",
    "ApprovalInvalid", "ApprovalRequired", "JarvisCoreError", "KillSwitchEngaged",
    "PolicyDenied", "RecordIntegrityError", "SubjectForgotten",
    "ClaimToken", "IdempotencyLedger", "derive_key",
    "FileKillSwitch", "KillSwitch", "NullKillSwitch",
    "CanonicalMemory", "Fact", "MemoryClass", "Provenance",
    "EvidenceRef", "Proposal", "QuarantinedWorker",
    "CapabilityRouter", "ClaimOutcome", "DuplicateSuppressed", "NoBackendAvailable",
    "TaskMismatch",
    "__version__",
]
__version__ = "0.1.0"
