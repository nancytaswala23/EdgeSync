import sys
sys.path.insert(0, "/app")

import pytest
from datetime import datetime

from models.models import ConnectivityStatus, ConflictResolution, SyncStatus
from storage.local_storage import LocalStorage
from sync.sync_engine import SyncEngine, CloudStorage


@pytest.fixture
def local():
    storage = LocalStorage(":memory:")
    yield storage
    storage.clear()


@pytest.fixture
def cloud():
    return CloudStorage()


@pytest.fixture
def engine(local, cloud):
    eng = SyncEngine(local, cloud, ConflictResolution.LATEST_WINS)
    eng.register_device("Kenya School", "education", "DEV-001")
    eng.register_device("Alaska Hospital", "healthcare", "DEV-002")
    return eng


class TestLocalStorage:
    def test_write_record(self, local):
        record = local.write("DEV-001", {"temp": 22.5, "humidity": 60})
        assert record.record_id is not None
        assert record.sync_status == SyncStatus.PENDING

    def test_get_pending(self, local):
        local.write("DEV-001", {"data": "a"})
        local.write("DEV-001", {"data": "b"})
        pending = local.get_pending("DEV-001")
        assert len(pending) == 2

    def test_mark_synced(self, local):
        record = local.write("DEV-001", {"data": "test"})
        local.mark_synced(record.record_id)
        pending = local.get_pending("DEV-001")
        assert len(pending) == 0

    def test_mark_failed_increments_retry(self, local):
        record = local.write("DEV-001", {"data": "test"})
        local.mark_failed(record.record_id)
        stats = local.get_stats("DEV-001")
        assert stats.get("failed", 0) == 1

    def test_requeue_failed(self, local):
        record = local.write("DEV-001", {"data": "test"})
        local.mark_failed(record.record_id)
        requeued = local.requeue_failed(max_retries=3)
        assert requeued == 1

    def test_get_stats(self, local):
        local.write("DEV-001", {"data": "a"})
        local.write("DEV-001", {"data": "b"})
        stats = local.get_stats("DEV-001")
        assert stats.get("pending", 0) == 2


class TestDeviceManagement:
    def test_register_device(self, engine):
        device = engine.register_device("Remote Village", "iot", "DEV-TEST")
        assert device.device_id == "DEV-TEST"
        assert device.connectivity == ConnectivityStatus.OFFLINE

    def test_restore_connectivity(self, engine):
        engine.restore_connectivity("DEV-001")
        device = engine.get_device("DEV-001")
        assert device.connectivity == ConnectivityStatus.ONLINE

    def test_lose_connectivity(self, engine):
        engine.restore_connectivity("DEV-001")
        engine.lose_connectivity("DEV-001")
        device = engine.get_device("DEV-001")
        assert device.connectivity == ConnectivityStatus.OFFLINE


class TestSyncEngine:
    def test_sync_pending_records(self, engine, local, cloud):
        # Write records while offline
        local.write("DEV-001", {"reading": 1})
        local.write("DEV-001", {"reading": 2})
        local.write("DEV-001", {"reading": 3})

        # Restore connectivity and sync
        engine.restore_connectivity("DEV-001")
        result = engine.sync("DEV-001")

        assert result.synced == 3
        assert result.failed == 0
        assert cloud.count() == 3

    def test_sync_fails_when_offline(self, engine, local):
        local.write("DEV-001", {"data": "test"})
        with pytest.raises(ConnectionError):
            engine.sync("DEV-001")

    def test_sync_history_recorded(self, engine, local):
        local.write("DEV-001", {"data": "test"})
        engine.restore_connectivity("DEV-001")
        engine.sync("DEV-001")

        history = engine.get_sync_history()
        assert len(history) == 1
        assert history[0].device_id == "DEV-001"

    def test_device_last_sync_updated(self, engine, local):
        local.write("DEV-001", {"data": "test"})
        engine.restore_connectivity("DEV-001")
        engine.sync("DEV-001")

        device = engine.get_device("DEV-001")
        assert device.last_sync is not None


class TestConflictResolution:
    def test_local_wins_strategy(self, local, cloud):
        eng = SyncEngine(local, cloud, ConflictResolution.LOCAL_WINS)
        eng.register_device("Test", "test", "DEV-CONF")

        # Pre-populate cloud with same record
        record = local.write("DEV-CONF", {"value": "local"})
        cloud_record = record
        cloud_record.payload = {"value": "remote"}
        cloud.put(cloud_record)

        # Sync — local should win
        eng.restore_connectivity("DEV-CONF")
        result = eng.sync("DEV-CONF")
        assert result.conflicts_resolved == 1

    def test_empty_sync_returns_zero(self, engine):
        engine.restore_connectivity("DEV-001")
        result = engine.sync("DEV-001")
        assert result.synced == 0
        assert result.total_records == 0
