from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class SessionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AnalysisSession:
    id: str
    source_id: str
    status: SessionStatus = SessionStatus.PENDING
    interval_seconds: float = 30.0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.now)

    def mark_started(self) -> None:
        self.status = SessionStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self) -> None:
        self.status = SessionStatus.COMPLETED
        self.finished_at = datetime.now()

    def mark_failed(self, message: str) -> None:
        self.status = SessionStatus.FAILED
        self.finished_at = datetime.now()
        self.error_message = message

    def mark_cancelled(self) -> None:
        self.status = SessionStatus.CANCELLED
        self.finished_at = datetime.now()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "status": self.status.value,
            "interval_seconds": self.interval_seconds,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AnalysisSession":
        def _parse(v: str | None) -> datetime | None:
            return datetime.fromisoformat(v) if v else None

        return cls(
            id=data["id"],
            source_id=data["source_id"],
            status=SessionStatus(data.get("status", "pending")),
            interval_seconds=float(data.get("interval_seconds", 30.0)),
            started_at=_parse(data.get("started_at")),
            finished_at=_parse(data.get("finished_at")),
            error_message=data.get("error_message"),
            created_at=_parse(data.get("created_at")) or datetime.now(),
        )
