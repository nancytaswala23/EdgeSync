import logging
import time
import uuid
from datetime import datetime
from typing import List, Dict, Optional

from models.models import (
    ConflictResolution,
    ConnectivityStatus,
    DataRecord,
    Device,
    SyncResult,
    SyncStatus,
)
from storage.local_storage import LocalStorage

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 1.0


class CloudStorage:
    """
    Simulated cloud storage (DynamoDB in production).
    In production, replace _store with boto3 DynamoDB calls.
    """
    def __init__(self):
        self._store: Dict[str, DataRecord] = {}

    def put(self, record: DataRecord) -> bool:
        self._store[record.record_id] = record
        return True

    def get(self, record_id: str) -> Optional[DataRecord]:
        return self._store.get(record_id)

    def exists(self, record_id: str) -> bool:
        return record_id in self._store

    def get_all(self) -> List[DataRecord]:
        return list(self._store.values())

    def count(self) -> int:
        return len(self._store)


class SyncEngine:
    """
    Core sync engine for EdgeSync.

    Handles:
    - Syncing pending local records to cloud when connectivity restores
    - Conflict resolution (latest_wins, local_wins, remote_wins)
    - Exponential backoff retry on failure
    - Full sync audit trail
    """

    def __init__(
        self,
        local_storage: LocalStorage,
        cloud_storage: CloudStorage,
        conflict_strategy: ConflictResolution = ConflictResolution.LATEST_WINS,
    ):
        self.local = local_storage
        self.cloud = cloud_storage
        self.conflict_strategy = conflict_strategy
        self._devices: Dict[str, Device] = {}
        self._sync_history: List[SyncResult] = []

    def register_device(
        self,
        location: str,
        device_type: str,
        device_id: Optional[str] = None,
    ) -> Device:
        """Register a remote device."""
        did = device_id or f"DEV-{str(uuid.uuid4())[:8].upper()}"
        device = Device(
            device_id=did,
            location=location,
            device_type=device_type,
            connectivity=ConnectivityStatus.OFFLINE,
        )
        self._devices[did] = device
        logger.info(f"Device {did} registered at {location}")
        return device

    def restore_connectivity(self, device_id: str) -> bool:
        """Signal that a device has regained Leo satellite connectivity."""
        device = self._devices.get(device_id)
        if not device:
            return False
        device.connectivity = ConnectivityStatus.ONLINE
        logger.info(f"Device {device_id} connectivity RESTORED — triggering sync")
        return True

    def lose_connectivity(self, device_id: str) -> bool:
        """Signal that a device has lost connectivity."""
        device = self._devices.get(device_id)
        if not device:
            return False
        device.connectivity = ConnectivityStatus.OFFLINE
        logger.info(f"Device {device_id} connectivity LOST — data will queue locally")
        return True

    def sync(self, device_id: str) -> SyncResult:
        """
        Sync all pending local records to cloud for a device.
        Runs conflict resolution and exponential backoff retry.
        """
        device = self._devices.get(device_id)
        if not device:
            raise ValueError(f"Device {device_id} not registered")

        if device.connectivity == ConnectivityStatus.OFFLINE:
            raise ConnectionError(f"Device {device_id} is offline — cannot sync")

        start_time = time.time()
        pending = self.local.get_pending(device_id)

        synced = 0
        failed = 0
        conflicts_resolved = 0

        logger.info(f"Starting sync for {device_id} — {len(pending)} pending records")

        for record in pending:
            success, conflict = self._sync_record(record)

            if success:
                synced += 1
                if conflict:
                    conflicts_resolved += 1
            else:
                failed += 1

        # Requeue failed records under retry limit
        requeued = self.local.requeue_failed(MAX_RETRIES)

        duration_ms = (time.time() - start_time) * 1000
        device.last_sync = datetime.utcnow()
        device.total_records_synced += synced

        result = SyncResult(
            device_id=device_id,
            total_records=len(pending),
            synced=synced,
            failed=failed,
            conflicts_resolved=conflicts_resolved,
            duration_ms=round(duration_ms, 2),
        )
        self._sync_history.append(result)

        logger.info(
            f"Sync complete for {device_id}: "
            f"{synced} synced, {failed} failed, {conflicts_resolved} conflicts resolved"
        )
        return result

    def _sync_record(self, record: DataRecord):
        """
        Attempt to sync a single record with retry + backoff.
        Returns (success, had_conflict).
        """
        for attempt in range(MAX_RETRIES):
            try:
                conflict = False

                # Check for conflict
                if self.cloud.exists(record.record_id):
                    conflict = True
                    resolved = self._resolve_conflict(record)
                    if not resolved:
                        self.local.mark_failed(record.record_id)
                        return False, False

                # Push to cloud
                self.cloud.put(record)
                self.local.mark_synced(record.record_id)

                if conflict:
                    self.local.mark_conflict_resolved(
                        record.record_id,
                        self.conflict_strategy.value,
                    )

                return True, conflict

            except Exception as e:
                backoff = BASE_BACKOFF_SECONDS * (2 ** attempt)
                logger.warning(
                    f"Sync attempt {attempt + 1} failed for {record.record_id}: {e}. "
                    f"Retrying in {backoff}s"
                )
                time.sleep(backoff * 0.01)  # scaled down for tests

        self.local.mark_failed(record.record_id)
        return False, False

    def _resolve_conflict(self, local_record: DataRecord) -> bool:
        """
        Resolve conflict between local and remote versions.
        Strategies: latest_wins, local_wins, remote_wins.
        """
        remote_record = self.cloud.get(local_record.record_id)
        if not remote_record:
            return True  # no real conflict

        if self.conflict_strategy == ConflictResolution.LOCAL_WINS:
            logger.info(f"Conflict on {local_record.record_id}: local wins")
            return True

        elif self.conflict_strategy == ConflictResolution.REMOTE_WINS:
            logger.info(f"Conflict on {local_record.record_id}: remote wins — skipping local")
            self.local.mark_failed(local_record.record_id)
            return False

        else:  # LATEST_WINS
            if local_record.updated_at >= remote_record.updated_at:
                logger.info(f"Conflict on {local_record.record_id}: local is newer — local wins")
                return True
            else:
                logger.info(f"Conflict on {local_record.record_id}: remote is newer — remote wins")
                self.local.mark_failed(local_record.record_id)
                return False

    def get_device(self, device_id: str) -> Optional[Device]:
        return self._devices.get(device_id)

    def get_all_devices(self) -> List[Device]:
        return list(self._devices.values())

    def get_sync_history(self) -> List[SyncResult]:
        return self._sync_history

    def get_cloud_count(self) -> int:
        return self.cloud.count()
