from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any


class SyncStatus(Enum):
    PENDING = "pending"
    SYNCED = "synced"
    FAILED = "failed"
    CONFLICT = "conflict"
    RESOLVED = "resolved"


class ConnectivityStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"


class ConflictResolution(Enum):
    LOCAL_WINS = "local_wins"
    REMOTE_WINS = "remote_wins"
    LATEST_WINS = "latest_wins"


@dataclass
class DataRecord:
    """A single data record created by a remote device."""
    record_id: str
    device_id: str
    payload: Any
    created_at: datetime
    updated_at: datetime
    sync_status: SyncStatus = SyncStatus.PENDING
    retry_count: int = 0
    synced_at: Optional[datetime] = None
    conflict_resolved_by: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "device_id": self.device_id,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "sync_status": self.sync_status.value,
            "retry_count": self.retry_count,
            "synced_at": self.synced_at.isoformat() if self.synced_at else None,
            "conflict_resolved_by": self.conflict_resolved_by,
        }


@dataclass
class SyncResult:
    """Result of a sync operation."""
    device_id: str
    total_records: int
    synced: int
    failed: int
    conflicts_resolved: int
    duration_ms: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "total_records": self.total_records,
            "synced": self.synced,
            "failed": self.failed,
            "conflicts_resolved": self.conflicts_resolved,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Device:
    """A remote device (school, hospital, etc.)."""
    device_id: str
    location: str
    device_type: str
    connectivity: ConnectivityStatus = ConnectivityStatus.OFFLINE
    last_sync: Optional[datetime] = None
    total_records_synced: int = 0

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "location": self.location,
            "device_type": self.device_type,
            "connectivity": self.connectivity.value,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "total_records_synced": self.total_records_synced,
        }
