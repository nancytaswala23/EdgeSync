import sqlite3
import json
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime
from typing import List, Optional

from models.models import DataRecord, SyncStatus

logger = logging.getLogger(__name__)

DB_PATH = "edgesync_local.db"


class LocalStorage:
    """
    SQLite-based local storage for remote devices.
    Queues data records during connectivity outages.
    Acts as the offline buffer before syncing to cloud.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        if db_path == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
        else:
            self._memory_conn = None
        self._init_db()

    def _get_conn(self):
        if self._memory_conn:
            return self._memory_conn
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS records (
                record_id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                synced_at TEXT,
                conflict_resolved_by TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_status ON records(sync_status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_device_id ON records(device_id)")
        conn.commit()
        logger.info(f"Local storage initialized at {self.db_path}")

    def write(self, device_id: str, payload: dict) -> DataRecord:
        now = datetime.utcnow()
        record = DataRecord(
            record_id=str(uuid.uuid4()),
            device_id=device_id,
            payload=payload,
            created_at=now,
            updated_at=now,
            sync_status=SyncStatus.PENDING,
        )
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO records
            (record_id, device_id, payload, created_at, updated_at, sync_status, retry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            record.record_id, record.device_id, json.dumps(record.payload),
            record.created_at.isoformat(), record.updated_at.isoformat(),
            record.sync_status.value, record.retry_count,
        ))
        conn.commit()
        logger.info(f"Record {record.record_id} written to local storage")
        return record

    def get_pending(self, device_id: Optional[str] = None) -> List[DataRecord]:
        conn = self._get_conn()
        if device_id:
            rows = conn.execute("""
                SELECT * FROM records WHERE sync_status = 'pending' AND device_id = ?
                ORDER BY created_at ASC
            """, (device_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM records WHERE sync_status = 'pending' ORDER BY created_at ASC
            """).fetchall()
        return [self._row_to_record(row) for row in rows]

    def mark_synced(self, record_id: str) -> bool:
        conn = self._get_conn()
        conn.execute("""
            UPDATE records SET sync_status = 'synced', synced_at = ? WHERE record_id = ?
        """, (datetime.utcnow().isoformat(), record_id))
        conn.commit()
        return True

    def mark_failed(self, record_id: str) -> bool:
        conn = self._get_conn()
        conn.execute("""
            UPDATE records SET sync_status = 'failed', retry_count = retry_count + 1
            WHERE record_id = ?
        """, (record_id,))
        conn.commit()
        return True

    def mark_conflict_resolved(self, record_id: str, resolution: str) -> bool:
        conn = self._get_conn()
        conn.execute("""
            UPDATE records SET sync_status = 'resolved', conflict_resolved_by = ?
            WHERE record_id = ?
        """, (resolution, record_id))
        conn.commit()
        return True

    def requeue_failed(self, max_retries: int = 3) -> int:
        conn = self._get_conn()
        result = conn.execute("""
            UPDATE records SET sync_status = 'pending'
            WHERE sync_status = 'failed' AND retry_count < ?
        """, (max_retries,))
        conn.commit()
        requeued = result.rowcount
        if requeued:
            logger.info(f"Requeued {requeued} failed records")
        return requeued

    def get_stats(self, device_id: Optional[str] = None) -> dict:
        conn = self._get_conn()
        if device_id:
            rows = conn.execute("""
                SELECT sync_status, COUNT(*) FROM records WHERE device_id = ? GROUP BY sync_status
            """, (device_id,)).fetchall()
        else:
            rows = conn.execute("""
                SELECT sync_status, COUNT(*) FROM records GROUP BY sync_status
            """).fetchall()
        return {row[0]: row[1] for row in rows}

    def clear(self):
        conn = self._get_conn()
        conn.execute("DELETE FROM records")
        conn.commit()

    def _row_to_record(self, row) -> DataRecord:
        return DataRecord(
            record_id=row[0], device_id=row[1], payload=json.loads(row[2]),
            created_at=datetime.fromisoformat(row[3]),
            updated_at=datetime.fromisoformat(row[4]),
            sync_status=SyncStatus(row[5]), retry_count=row[6],
            synced_at=datetime.fromisoformat(row[7]) if row[7] else None,
            conflict_resolved_by=row[8],
        )
