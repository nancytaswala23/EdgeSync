# 🌍 EdgeSync

**Offline-First Data Sync for Remote Devices — Powered by Leo Satellite Connectivity**

[![CI](https://github.com/nancytaswala23/edgesync/actions/workflows/ci.yml/badge.svg)](https://github.com/nancytaswala23/edgesync/actions)
![Python](https://img.shields.io/badge/python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110-green)
![SQLite](https://img.shields.io/badge/local-SQLite-blue)
![DynamoDB](https://img.shields.io/badge/cloud-DynamoDB--ready-orange)

---

## 📡 Overview

EdgeSync solves a core problem for LEO satellite networks: remote devices (schools, hospitals, weather stations) in areas without reliable internet need to **keep working offline** and **sync their data when satellite connectivity is restored**.

EdgeSync provides offline-first local storage, automatic cloud sync with conflict resolution, and exponential backoff retry — exactly the infrastructure needed to serve the billions of people Amazon Leo is connecting.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     EdgeSync System                          │
│                                                             │
│  Remote Device (School/Hospital)                            │
│  ┌──────────────────────────────────┐                       │
│  │  Write Data (always works)       │                       │
│  │         ↓                        │                       │
│  │  Local SQLite Queue              │                       │
│  │  (offline buffer)                │                       │
│  └──────────────┬───────────────────┘                       │
│                 │ Leo Satellite Signal Restored              │
│                 ↓                                           │
│  ┌──────────────────────────────────┐                       │
│  │  Sync Engine                     │                       │
│  │  - Conflict Resolution           │                       │
│  │    (latest_wins / local_wins     │                       │
│  │     / remote_wins)               │                       │
│  │  - Exponential Backoff Retry     │                       │
│  │  - Full Audit Trail              │                       │
│  └──────────────┬───────────────────┘                       │
│                 ↓                                           │
│  ┌──────────────────────────────────┐                       │
│  │  Cloud Storage (AWS DynamoDB)    │                       │
│  │  (production-ready)              │                       │
│  └──────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

---

## ✨ Key Features

- **Offline-First** — devices write data locally even with zero connectivity
- **Auto Sync** — triggers automatically when Leo satellite signal is restored
- **Conflict Resolution** — 3 strategies: `latest_wins`, `local_wins`, `remote_wins`
- **Exponential Backoff** — failed syncs retry with increasing delays
- **Full Audit Trail** — every sync operation logged with timestamp and stats
- **SQL + NoSQL** — SQLite locally, DynamoDB-ready for cloud
- **REST API** — full FastAPI service with Swagger docs
- **CI/CD** — GitHub Actions runs tests on every push

---

## 🚀 Quick Start

```bash
git clone https://github.com/nancytaswala23/edgesync.git
cd edgesync

# Run with Docker
docker-compose up --build

# API at http://localhost:8002
# Docs at http://localhost:8002/docs
```

---

## 📮 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/devices/register` | Register a remote device |
| GET | `/devices` | All devices + connectivity status |
| POST | `/devices/{id}/write` | Write data locally (works offline) |
| POST | `/devices/{id}/connectivity/restore` | Signal Leo connectivity restored |
| POST | `/devices/{id}/connectivity/lose` | Signal connectivity lost |
| POST | `/devices/{id}/sync` | Trigger sync to cloud |
| GET | `/devices/{id}/queue` | View pending records |
| GET | `/cloud/records` | All synced cloud records |
| GET | `/sync/history` | Full sync history |

---

## 🧪 Demo Flow

```bash
# 1. Write data while offline (school attendance, health records)
curl -X POST http://localhost:8002/devices/DEV-SCHOOL-01/write \
  -H "Content-Type: application/json" \
  -d '{"device_id": "DEV-SCHOOL-01", "payload": {"students": 42, "date": "2026-03-05"}}'

# 2. Leo satellite passes overhead — connectivity restored!
curl -X POST http://localhost:8002/devices/DEV-SCHOOL-01/connectivity/restore

# 3. Sync all queued data to cloud
curl -X POST http://localhost:8002/devices/DEV-SCHOOL-01/sync

# Response:
# {"synced": 3, "failed": 0, "conflicts_resolved": 0, "duration_ms": 12.4}
```

---

## 🗂️ Project Structure

```
edgesync/
├── sync/
│   └── sync_engine.py      # Core sync + conflict resolution + retry
├── storage/
│   └── local_storage.py    # SQLite offline buffer
├── api/
│   └── main.py             # FastAPI REST layer
├── models/
│   └── models.py           # OOP data classes
├── tests/
│   └── test_edgesync.py    # Full test suite
├── .github/workflows/
│   └── ci.yml              # GitHub Actions CI
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 🌍 Real-World Relevance

Amazon Leo's mission is connecting schools, hospitals, and communities without internet. EdgeSync directly addresses their core infrastructure challenge: **what happens to data when the satellite isn't overhead?** This system ensures zero data loss and seamless sync when connectivity is restored.
