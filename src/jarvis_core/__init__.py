"""Jarvis Core.

The small, permanent layer: identity, capability routing, policy, canonical
memory, the Record, and the proactivity plane.

Design invariant (docs/05 §1): **no module in this package may import a vendor
type.** Control planes, agent runtimes and model providers live behind adapters.
If a file here needs to know what OpenClaw or Hermes or Anthropic is, it is in
the wrong package.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
