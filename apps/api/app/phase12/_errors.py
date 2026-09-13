"""Phase 12 shared exceptions (import-safe: no engine dependencies).

Defined here so ``engine.py`` and ``governance.py`` can import them without a
circular dependency (governance raises budget denials that the engine catches
and marks the run FAILED).
"""

from __future__ import annotations


class SimulationEngineError(ValueError):
    """A simulation lifecycle or execution error."""


class SimulationSandboxRefusalError(SimulationEngineError):
    """A behavior attempted a production/external side effect inside the sim.

    The closed sandbox refuses it (SimulationEventKind.SANDBOX_REFUSAL is
    recorded) and the run is failed — the simulation can never trigger real
    side effects (no HTTP, email, browser, financial transaction, DB mutation).
    """


__all__ = ["SimulationEngineError", "SimulationSandboxRefusalError"]
