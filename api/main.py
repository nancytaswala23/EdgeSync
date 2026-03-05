import sys
sys.path.insert(0, "/app")

from datetime import datetime
from typing import Optional
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from sync.sync_engine import SyncEngine, CloudStorage
from storage.local_storage import LocalStorage
from models.models import ConflictResolution

app = FastAPI(
    title="EdgeSync API",
    description="Offline-First Data Sync for Remote Devices — Powered by Leo Satellite Connectivity",
    version="1.0.0",
)

local_storage = LocalStorage(":memory:")  # in-memory SQLite for demo
cloud_storage = CloudStorage()
engine = SyncEngine(local_storage, cloud_storage, ConflictResolution.LATEST_WINS)


# ── Seed devices on startup ───────────────────────────────────────────────────
@app.on_event("startup")
def seed_devices():
    engine.register_device("Rural School — Kenya", "education", "DEV-SCHOOL-01")
    engine.register_device("Remote Hospital — Alaska", "healthcare", "DEV-HOSP-01")
    engine.register_device("Weather Station — Antarctica", "sensor", "DEV-WTHR-01")


# ── Request schemas ────────────────────────────────────────────────────────────
class WriteRequest(BaseModel):
    device_id: str
    payload: dict


class RegisterRequest(BaseModel):
    location: str
    device_type: str
    device_id: Optional[str] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "EdgeSync",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/devices/register")
def register_device(req: RegisterRequest):
    """Register a new remote device."""
    device = engine.register_device(req.location, req.device_type, req.device_id)
    return {"message": "Device registered", "device": device.to_dict()}


@app.get("/devices")
def get_devices():
    """Get all registered devices and their status."""
    devices = engine.get_all_devices()
    return {
        "total": len(devices),
        "online": sum(1 for d in devices if d.connectivity.value == "online"),
        "offline": sum(1 for d in devices if d.connectivity.value == "offline"),
        "devices": [d.to_dict() for d in devices],
    }


@app.post("/devices/{device_id}/write")
def write_record(device_id: str, req: WriteRequest):
    """
    Write data locally on a device.
    Works even when offline — queues for later sync.
    """
    record = local_storage.write(device_id, req.payload)
    return {
        "message": "Record queued locally",
        "record": record.to_dict(),
    }


@app.post("/devices/{device_id}/connectivity/restore")
def restore_connectivity(device_id: str):
    """Signal that Leo satellite connectivity has been restored."""
    success = engine.restore_connectivity(device_id)
    if not success:
        raise HTTPException(404, f"Device {device_id} not found")
    return {"message": f"Connectivity restored for {device_id}"}


@app.post("/devices/{device_id}/connectivity/lose")
def lose_connectivity(device_id: str):
    """Signal that device has lost connectivity."""
    success = engine.lose_connectivity(device_id)
    if not success:
        raise HTTPException(404, f"Device {device_id} not found")
    return {"message": f"Connectivity lost for {device_id} — data will queue locally"}


@app.post("/devices/{device_id}/sync")
def sync_device(device_id: str):
    """
    Trigger sync for a device.
    Pushes all pending local records to cloud with conflict resolution.
    """
    try:
        result = engine.sync(device_id)
        return {"message": "Sync complete", "result": result.to_dict()}
    except ConnectionError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/devices/{device_id}/queue")
def get_queue(device_id: str):
    """Get pending records waiting to sync for a device."""
    pending = local_storage.get_pending(device_id)
    stats = local_storage.get_stats(device_id)
    return {
        "device_id": device_id,
        "pending_count": len(pending),
        "stats": stats,
        "records": [r.to_dict() for r in pending],
    }


@app.get("/cloud/records")
def get_cloud_records():
    """View all records successfully synced to cloud."""
    records = cloud_storage.get_all()
    return {
        "total_synced": len(records),
        "records": [r.to_dict() for r in records],
    }


@app.get("/sync/history")
def get_sync_history():
    """Full sync history across all devices."""
    history = engine.get_sync_history()
    return {
        "total_syncs": len(history),
        "history": [r.to_dict() for r in history],
    }


if __name__ == "__main__":
    uvicorn.run("api.main:app", host="0.0.0.0", port=8002, reload=True)
