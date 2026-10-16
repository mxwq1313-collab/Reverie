import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ImportIssue:
    entity: str
    index: int | None
    code: str
    message: str
    field: str | None = None
    record_id: str | None = None
    line: int | None = None


@dataclass(slots=True)
class ImportReport:
    source: str
    format: str
    database: str
    import_id: str = field(default_factory=lambda: uuid4().hex)
    started_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    status: str = "failed"
    source_namespace: str | None = None
    source_metadata: dict = field(default_factory=dict)
    users: int = 0
    chats: int = 0
    messages: int = 0
    users_created_count: int = 0
    users_reused_count: int = 0
    users_failed_count: int = 0
    chats_created_count: int = 0
    chats_reused_count: int = 0
    chats_failed_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    duplicated_count: int = 0
    duration_seconds: float = 0.0
    strict: bool = False
    rolled_back: bool = False
    migration_backup: str | None = None
    report_path: str | None = None
    issues: list[ImportIssue] = field(default_factory=list)
    warnings: list[ImportIssue] = field(default_factory=list)
    identity_strategy: str = "legacy-content"
    source_capabilities: dict = field(default_factory=dict)

    def to_dict(self):
        result = asdict(self)
        result.update(success=self.success_count, failed=self.failed_count, time=f"{self.duration_seconds:.3f}s")
        return result

    def save(self, directory):
        directory = Path(directory).expanduser().resolve()
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{self.started_at[:19].replace(':', '').replace('-', '')}_{self.import_id}.json"
        temporary = target.with_suffix(".json.tmp")
        self.report_path = str(target)
        try:
            with temporary.open("x", encoding="utf-8", newline="\n") as handle:
                json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        except OSError:
            self.report_path = None
            if temporary.exists():
                temporary.unlink()
            raise
        return target
