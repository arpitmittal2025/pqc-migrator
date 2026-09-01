"""Optimization pass -- deliberately a stub for Project-I.

Scope note (CLAUDE.md section 2): performance/size optimization of migrated PQC
code is out of scope for this build. The interface is fixed here so Project-II
can fill it in without touching the pipeline.
"""

from __future__ import annotations

from ..models import MigrationResult


def optimize(results: list[MigrationResult]) -> list[MigrationResult]:
    """Return the migrations unchanged.

    # TODO(project-II): parameter-set tuning, batched keygen, hybrid
    # classical+PQC modes, and code-size/latency refactoring of migrated call
    # sites. Nothing is optimized in Project-I, so this must not pretend to.
    """
    return list(results)


def available() -> bool:
    """Whether an optimization backend is implemented. Always False in Project-I."""
    return False
