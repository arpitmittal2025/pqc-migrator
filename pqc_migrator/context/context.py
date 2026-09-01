"""Application context: how strong the replacement has to be, and what shape.

The context is either read from a ``pqc.config.json`` next to (or above) the
scanned code, or inferred with documented defaults.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

CONFIG_NAME = "pqc.config.json"

DEFAULT_SECURITY_LEVEL = 3
SIGNATURE_SCHEMES = ("ML-DSA", "SLH-DSA")


@dataclass
class AppContext:
    """Deployment context that steers the recommender."""

    security_level: int = DEFAULT_SECURITY_LEVEL  # target NIST category 1..5
    prefer_signature_scheme: str = "ML-DSA"  # "ML-DSA" | "SLH-DSA"
    source: str = "defaults"  # config path, or "defaults"
    notes: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        return data


def find_config(path: str | Path) -> Path | None:
    """Look for ``pqc.config.json`` in the target dir, then its parents."""
    start = Path(path)
    start = start if start.is_dir() else start.parent
    for candidate in [start, *start.parents]:
        config = candidate / CONFIG_NAME
        if config.is_file():
            return config
    return None


def _coerce_level(value: Any) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return DEFAULT_SECURITY_LEVEL
    return min(5, max(1, level))


def load_context(path: str | Path, config_path: str | Path | None = None) -> AppContext:
    """Load context for ``path``; falls back to documented defaults."""
    config = Path(config_path) if config_path else find_config(path)
    if config is None or not config.is_file():
        return AppContext(
            source="defaults",
            notes=(
                f"No {CONFIG_NAME} found; assuming NIST level "
                f"{DEFAULT_SECURITY_LEVEL} and ML-DSA signatures."
            ),
        )

    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return AppContext(
            source="defaults",
            notes=f"Could not read {config}: {exc}. Using defaults.",
        )

    if not isinstance(data, dict):
        return AppContext(source="defaults", notes=f"{config} is not a JSON object.")

    scheme = str(data.get("prefer_signature_scheme", "ML-DSA")).upper()
    if scheme not in SIGNATURE_SCHEMES:
        scheme = "ML-DSA"

    return AppContext(
        security_level=_coerce_level(data.get("security_level", DEFAULT_SECURITY_LEVEL)),
        prefer_signature_scheme=scheme,
        source=str(config),
        notes=str(data.get("notes", "")),
        raw=data,
    )
