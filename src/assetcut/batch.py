from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

BatchStatus = Literal["processed", "skipped", "failed"]


@dataclass(frozen=True)
class BatchRecord:
    input: str
    output: str
    status: BatchStatus
    ok: bool
    validation: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BatchSummary:
    found: int
    processed: int
    skipped: int
    failed: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)
