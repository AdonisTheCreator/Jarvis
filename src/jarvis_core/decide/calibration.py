"""Calibration tracking (D9 §6).

The entire value proposition of a decision model is that its probabilities are
*calibrated*. If the 0.8 bucket is not right about 80% of the time, every
threshold in the catalog is meaningless.

We verify this against **our own** outcomes rather than the vendor's numbers,
because calibration is domain-specific and there is no reason to assume it
transfers to our state shapes. The Record already logs every decision and its
outcome (D5), so the dataset exists for free.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

DEFAULT_BUCKETS: tuple[float, ...] = (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 1.01)


@dataclass(frozen=True, slots=True)
class Observation:
    """One decision whose real outcome later became known."""

    point_id: str
    confidence: float
    correct: bool

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            # An out-of-range confidence falls outside every bucket while still
            # counting in n, which divides ECE down and makes a miscalibrated
            # point look better than it is. Fail here instead.
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Bucket:
    low: float
    high: float
    count: int
    mean_confidence: float
    accuracy: float

    @property
    def gap(self) -> float:
        """How far predicted confidence sits from observed accuracy."""
        return abs(self.mean_confidence - self.accuracy)


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    """Reliability diagram plus the two scalar scores worth tracking."""

    point_id: str
    n: int
    buckets: tuple[Bucket, ...]
    brier: float
    ece: float
    """Expected Calibration Error: the sample-weighted mean bucket gap."""

    def verdict(self, *, max_ece: float = 0.1, min_samples: int = 50) -> str:
        """``ok``, ``insufficient-data`` or ``miscalibrated``.

        The last two both mean "do not believe the thresholds" and call for
        opposite responses: one needs more traffic, the other needs the point
        demoted. Collapsing them into a single SUSPECT gets a perfectly
        calibrated new point demoted for the crime of being new.
        """
        if self.n < min_samples:
            return "insufficient-data"
        return "ok" if self.ece <= max_ece else "miscalibrated"

    def is_trustworthy(self, *, max_ece: float = 0.1, min_samples: int = 50) -> bool:
        """Whether thresholds on this point should still be believed."""
        return self.verdict(max_ece=max_ece, min_samples=min_samples) == "ok"

    def summary(self) -> str:
        return (
            f"{self.point_id}: n={self.n} brier={self.brier:.3f} "
            f"ece={self.ece:.3f} [{self.verdict()}]"
        )


class CalibrationLog:
    """Accumulates observations and produces per-point reports.

    Tracked **per decision point id** -- supersession detection and flake
    classification will calibrate very differently, and a global number would
    hide both.
    """

    def __init__(self, buckets: Sequence[float] = DEFAULT_BUCKETS) -> None:
        self._edges = tuple(buckets)
        self._by_point: dict[str, list[Observation]] = {}

    def record(self, point_id: str, confidence: float, correct: bool) -> None:
        self._by_point.setdefault(point_id, []).append(
            Observation(point_id, confidence, correct)
        )

    def extend(self, observations: Iterable[Observation]) -> None:
        for observation in observations:
            self.record(observation.point_id, observation.confidence, observation.correct)

    def point_ids(self) -> Sequence[str]:
        return sorted(self._by_point)

    def report(self, point_id: str) -> CalibrationReport:
        observations = self._by_point.get(point_id, [])
        n = len(observations)
        if n == 0:
            return CalibrationReport(point_id, 0, (), brier=0.0, ece=0.0)

        brier = sum((o.confidence - (1.0 if o.correct else 0.0)) ** 2 for o in observations) / n

        buckets: list[Bucket] = []
        weighted_gap = 0.0
        for low, high in zip(self._edges, self._edges[1:]):
            members = [o for o in observations if low <= o.confidence < high]
            if not members:
                continue
            mean_confidence = sum(o.confidence for o in members) / len(members)
            accuracy = sum(1 for o in members if o.correct) / len(members)
            bucket = Bucket(low, high, len(members), mean_confidence, accuracy)
            buckets.append(bucket)
            weighted_gap += bucket.gap * len(members)

        return CalibrationReport(
            point_id=point_id,
            n=n,
            buckets=tuple(buckets),
            brier=brier,
            ece=weighted_gap / n,
        )

    def untrustworthy(
        self, *, max_ece: float = 0.1, min_samples: int = 50
    ) -> Mapping[str, CalibrationReport]:
        """Points whose calibration has gone bad and should be demoted.

        A point that fails here is dropped to its deterministic fallback with a
        notice -- per point, never globally. Points with too little traffic are
        *not* included: they have not been shown to be wrong, only to be new.

        The thresholds are named parameters rather than ``**kwargs`` on
        purpose. A misspelled one used to be swallowed and the default applied,
        so a caller asking for a strict bar quietly got a lax one.
        """
        return {
            point_id: report
            for point_id in self.point_ids()
            if (report := self.report(point_id)).verdict(
                max_ece=max_ece, min_samples=min_samples
            ) == "miscalibrated"
        }
