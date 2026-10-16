"""Shared plumbing for every first-party Maestro service.

Domain knowledge never lives here (see ADR-0007); this package is transport, identity,
telemetry and the LLM loop. Each module is independent and documented in place.
"""

from maestro_common.config import Settings, settings

__all__ = ["Settings", "settings"]
