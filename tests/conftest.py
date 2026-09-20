import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jarvis_core.capability import Capability, CapabilityRegistry, PrivacyClass
from jarvis_core.policy import ApprovalLedger, AutonomyClass as A, PolicyEngine, ProtocolRegistry
from jarvis_core.record import RecordStore, SubjectKeystore


@pytest.fixture
def keystore() -> SubjectKeystore:
    return SubjectKeystore(os.urandom(32))


@pytest.fixture
def store(tmp_path: Path, keystore: SubjectKeystore) -> RecordStore:
    return RecordStore(tmp_path / "record", keystore)


@pytest.fixture
def registry() -> CapabilityRegistry:
    return CapabilityRegistry(
        [
            Capability("ci.read_status", A.A0_OBSERVE, enabled=True),
            Capability("ci.rerun_job", A.A1_REVERSIBLE, enabled=True,
                       idempotency_key_fields=("job_id",)),
            Capability("message.send", A.A2_EXTERNAL, enabled=True,
                       idempotency_key_fields=("to", "body")),
            Capability("door.unlock", A.A3_CONSEQUENTIAL, enabled=True, reversible=False,
                       privacy=PrivacyClass.SENSITIVE),
            Capability("vehicle.drive", A.A4_BLOCKED, enabled=True),
            Capability("ci.read_logs", A.A0_OBSERVE, enabled=False),
        ]
    )


@pytest.fixture
def approvals() -> ApprovalLedger:
    return ApprovalLedger(os.urandom(32))


@pytest.fixture
def protocols(registry: CapabilityRegistry) -> ProtocolRegistry:
    return ProtocolRegistry(registry.classes())


@pytest.fixture
def engine(registry, approvals, protocols) -> PolicyEngine:
    return PolicyEngine(registry, approvals, protocols)
