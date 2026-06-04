# Copyright 2026 Muhammad Waleed & Areeba
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import json
import uuid
import logging
from sqlalchemy import text
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

import valkey.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from database import db_manager, IncidentRecord, ApprovalRecord

# ─── Environment Configuration ───────────────────────────────────────────────
LOG_DIR = os.getenv("TAAFI_LOG_DIR", "./logs")
VALKEY_URL = os.getenv("VALKEY_URL", "redis://valkey:6379")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if o.strip()
]
INCIDENT_CHANNEL = "taafi:incidents"
REMEDIATION_CHANNEL = "taafi:remediation"

os.makedirs(LOG_DIR, exist_ok=True)
INCIDENT_LOG_PATH = os.path.join(LOG_DIR, "active_incidents.log")

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("core-engine.main")

# ─── FastAPI App ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Taafi.ai Core Engine",
    description="Automated SRE database incident remediation platform – cloud-native edition.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Valkey Client (module-level, initialised on startup) ────────────────────
valkey_client: Optional[aioredis.Valkey] = None


async def get_valkey() -> aioredis.Valkey:
    """FastAPI dependency that returns the shared Valkey client."""
    if valkey_client is None:
        raise HTTPException(status_code=503, detail="Valkey unavailable")
    return valkey_client


# ─── Pydantic Models ──────────────────────────────────────────────────────────
class DeadlockReport(BaseModel):
    database_name: str
    blocking_query: str
    blocked_query: str
    transaction_ids: List[str]
    lock_types: List[str]
    schema_dump: Optional[str] = None


class RemediatePayload(BaseModel):
    incident_id: str
    suggested_patch: str
    reasoning: str
    tool: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None


class ApprovalAction(BaseModel):
    comment: Optional[str] = None


class ApprovalPayload(BaseModel):
    approval_id: str
    incident_id: str
    patch_sql: str
    tool: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    reasoning: Optional[str] = None
    risk_level: Optional[str] = "HIGH"



# ─── Helpers ──────────────────────────────────────────────────────────────────
def extract_table_names(q1: str, q2: str) -> List[str]:
    """Parse table names involved in circular locks from queries."""
    tables = []
    for q in [q1, q2]:
        for t in ["users", "transactions", "orders", "accounts"]:
            if t in q.lower() and t not in tables:
                tables.append(t)
    return tables


def _write_audit_log(level: str, category: str, details: Dict[str, Any]):
    """Write-only audit log – never read by application logic."""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,
        "category": category,
        "details": details,
    }
    with open(INCIDENT_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def _publish_event(channel: str, category: str, level: str, details: Dict[str, Any]):
    """Publish a standardized JSON payload to a Valkey channel."""
    if valkey_client:
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": level,
            "category": category,
            "details": details,
        }
        await valkey_client.publish(channel, json.dumps(payload))



# ─── App Lifecycle ────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup_event():
    global valkey_client
    try:
        valkey_client = aioredis.Valkey.from_url(VALKEY_URL, decode_responses=True)
        await valkey_client.ping()
        logger.info("Connected to Valkey at %s", VALKEY_URL)
    except Exception as exc:
        logger.error("Could not connect to Valkey: %s – SSE streaming degraded.", exc)
        valkey_client = None

    # Ensure DB schema is created
    db_manager.create_tables()
    logger.info("Taafi.ai Core Engine v2 started.")


@app.on_event("shutdown")
async def shutdown_event():
    if valkey_client:
        await valkey_client.aclose()


# ─── Health Probes ────────────────────────────────────────────────────────────
@app.get("/health/live", tags=["health"])
def liveness():
    """Kubernetes liveness probe – always 200 if the process is up."""
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
async def readiness():
    """Kubernetes readiness probe – checks DB and Valkey connectivity."""
    errors: List[str] = []

    # Check DB
    if not db_manager.verify_connection(retries=1, delay=0):
        errors.append("database unreachable")

    # Check Valkey
    if valkey_client is None:
        errors.append("valkey not initialised")
    else:
        try:
            await valkey_client.ping()
        except Exception:
            errors.append("valkey ping failed")

    if errors:
        raise HTTPException(status_code=503, detail={"ready": False, "errors": errors})
    return {"status": "ready"}


# ─── SSE Stream (Valkey Pub/Sub pass-through) ─────────────────────────────────
@app.get("/api/stream", tags=["stream"])
async def stream_terminal_logs():
    """
    Server-Sent Events – bridges the Valkey taafi:incidents channel
    to every connected browser tab. Completely stateless; no in-memory queues.
    """
    async def event_generator():
        # Send recent DB history first so the dashboard has instant context
        with db_manager.SessionLocal() as session:
            rows = (
                session.query(IncidentRecord)
                .order_by(IncidentRecord.created_at.desc())
                .limit(20)
                .all()
            )
            for row in reversed(rows):
                yield f"data: {json.dumps(row.to_dict())}\n\n"

        # Subscribe to Valkey channel for live updates
        if valkey_client is None:
            return
        pubsub = valkey_client.pubsub()
        await pubsub.subscribe(INCIDENT_CHANNEL, REMEDIATION_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    yield f"data: {message['data']}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── Incident APIs ────────────────────────────────────────────────────────────
@app.get("/api/incidents", tags=["incidents"])
def list_incidents():
    """Returns all incidents from PostgreSQL, newest first."""
    with db_manager.SessionLocal() as session:
        rows = (
            session.query(IncidentRecord)
            .order_by(IncidentRecord.created_at.desc())
            .all()
        )
        return [r.to_dict() for r in rows]


@app.post("/api/incidents/report", tags=["incidents"])
async def report_incident(incident: DeadlockReport):
    """Receives a deadlock report, persists it, and publishes to Valkey for the orchestrator."""
    incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
    details = {
        "incident_id": incident_id,
        "database_name": incident.database_name,
        "blocking_query": incident.blocking_query,
        "blocked_query": incident.blocked_query,
        "transaction_ids": incident.transaction_ids,
        "lock_types": incident.lock_types,
        "schema_dump": incident.schema_dump,
        "status": "UNRESOLVED",
    }

    # Persist to PostgreSQL
    with db_manager.SessionLocal() as session:
        record = IncidentRecord(
            incident_id=incident_id,
            category="DEADLOCK_TRAPPED",
            level="ERROR",
            details=json.dumps(details),
        )
        session.add(record)
        session.commit()

    # Write audit log
    _write_audit_log("ERROR", "DEADLOCK_TRAPPED", details)

    # Publish to Valkey – the neural-orchestrator subscribes here
    await _publish_event(INCIDENT_CHANNEL, "DEADLOCK_TRAPPED", "ERROR", details)

    return {"status": "success", "incident_id": incident_id}


@app.post("/api/incidents/simulate", tags=["incidents"])
async def simulate_deadlock():
    """Generates a realistic mock SQL deadlock for end-to-end demo validation."""
    incident_id = f"INC-SIM-{uuid.uuid4().hex[:6].upper()}"
    
    # ✅ Create actual tables in database for realistic simulation
    with db_manager.engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                active BOOLEAN
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER,
                status VARCHAR(20)
            )
        """))
        conn.commit()
    
    details = {
        "incident_id": incident_id,
        "database_name": "alibaba_rds_prod_users",
        "blocking_query": "UPDATE users SET active = TRUE WHERE id = 42;",
        "blocked_query": "UPDATE transactions SET status = 'COMPLETED' WHERE user_id = 42;",
        "transaction_ids": ["tx_0x94827", "tx_0x94828"],
        "lock_types": ["ExclusiveLock", "ShareLock"],
        "schema_dump": (
            "CREATE TABLE users (id SERIAL PRIMARY KEY, active BOOLEAN); "
            "CREATE TABLE transactions (id SERIAL PRIMARY KEY, user_id INTEGER, status VARCHAR(20));"
        ),
        "status": "QUEUED_FOR_REMEDIATION",
    }

    with db_manager.SessionLocal() as session:
        record = IncidentRecord(
            incident_id=incident_id,
            category="DEADLOCK_TRAPPED",
            level="ERROR",
            details=json.dumps(details),
        )
        session.add(record)
        session.commit()

    _write_audit_log("ERROR", "DEADLOCK_TRAPPED", details)
    await _publish_event(INCIDENT_CHANNEL, "DEADLOCK_TRAPPED", "ERROR", details)

    return {"status": "simulation_started", "incident_id": incident_id}


@app.get("/api/incidents/similar", tags=["incidents"])
def get_similar_incidents(
    table_names: Optional[str] = None,
    lock_types: Optional[str] = None,
    limit: int = 3
):
    """Retrieves top-N most similar past incidents based on table names and lock types."""
    target_tables = [t.strip().lower() for t in table_names.split(",") if t.strip()] if table_names else []
    target_locks = [l.strip().lower() for l in lock_types.split(",") if l.strip()] if lock_types else []

    with db_manager.SessionLocal() as session:
        from database import PatchHistoryRecord
        histories = session.query(PatchHistoryRecord).all()
        
        scored_histories = []
        for h in histories:
            h_tables = [t.lower() for t in json.loads(h.table_names)]
            h_locks = [l.lower() for l in json.loads(h.lock_types)]
            
            # Simple keyword matching score
            table_score = sum(1 for t in target_tables if t in h_tables)
            lock_score = sum(1 for l in target_locks if l in h_locks)
            total_score = table_score + lock_score
            
            scored_histories.append((total_score, h))
            
        # Sort by total_score desc, then h.created_at desc
        scored_histories.sort(key=lambda x: (x[0], x[1].created_at), reverse=True)
        
        results = [x[1].to_dict() for x in scored_histories[:limit]]
        return results



@app.post("/api/incidents/remediate", tags=["incidents"])
async def remediate_incident(payload: RemediatePayload):
    """
    Applies a verified healing SQL patch to the database.
    Executes with a 10-second statement timeout and full rollback on failure.
    Publishes REMEDIATION_COMPLETED or REMEDIATION_FAILED to Valkey.
    """
    incident_id = payload.incident_id
    patch = payload.suggested_patch.strip()

    _write_audit_log("INFO", "REMEDIATION_TRIGGERED", {
        "incident_id": incident_id,
        "patch": patch,
        "reasoning": payload.reasoning,
        "tool": payload.tool,
    })

    success = False
    error_msg = ""

    with db_manager.SessionLocal() as session:
        try:
            # Set a per-statement timeout (PostgreSQL-specific; ignored on SQLite)
            is_pg = db_manager.db_url.startswith("postgresql")
            if is_pg:
                session.execute(text("SET LOCAL statement_timeout = '10s'"))

            # Execute each statement in the patch
            for stmt in [s.strip() for s in patch.split(";") if s.strip()]:
                session.execute(text(stmt))

            session.commit()
            success = True
        except Exception as exc:
            session.rollback()
            error_msg = str(exc)
            logger.error("Remediation patch failed for %s: %s", incident_id, exc)

    # Update incident record in DB and write to patch_history
    with db_manager.SessionLocal() as session:
        record = session.query(IncidentRecord).filter_by(incident_id=incident_id).first()
        tables = []
        locks = []
        if record:
            details = json.loads(record.details)
            details["status"] = "RESOLVED" if success else "FAILED"
            details["patch_applied"] = patch
            details["reasoning"] = payload.reasoning
            details["error"] = error_msg
            record.details = json.dumps(details)
            
            q1 = details.get("blocking_query", "")
            q2 = details.get("blocked_query", "")
            tables = extract_table_names(q1, q2)
            locks = details.get("lock_types", [])
            session.commit()

        # Insert record into PatchHistoryRecord
        from database import PatchHistoryRecord
        history = PatchHistoryRecord(
            id=uuid.uuid4().hex[:16].upper(),
            incident_id=incident_id,
            table_names=json.dumps(tables),
            lock_types=json.dumps(locks),
            patch_sql=patch,
            tool=payload.tool,
            outcome="SUCCESS" if success else "FAILURE"
        )
        session.add(history)
        session.commit()

    result_category = "REMEDIATION_COMPLETED" if success else "REMEDIATION_FAILED"
    result_payload = {
        "category": result_category,
        "incident_id": incident_id,
        "success": success,
        "error": error_msg,
        "patch": patch,
        "tool": payload.tool,
        "reasoning": payload.reasoning,
        "timestamp": datetime.utcnow().isoformat(),
    }

    _write_audit_log("SUCCESS" if success else "ERROR", result_category, result_payload)
    await _publish_event(REMEDIATION_CHANNEL, result_category, "SUCCESS" if success else "ERROR", result_payload)

    if not success:
        raise HTTPException(status_code=500, detail={"status": "failed", "error": error_msg})

    return {"status": "resolved", "incident_id": incident_id}


# ─── Human-in-the-Loop Approval APIs ─────────────────────────────────────────
@app.get("/api/approvals", tags=["approvals"])
def list_approvals():
    """Returns all pending and resolved approval requests."""
    with db_manager.SessionLocal() as session:
        rows = (
            session.query(ApprovalRecord)
            .order_by(ApprovalRecord.created_at.desc())
            .all()
        )
        return [r.to_dict() for r in rows]


@app.post("/api/approvals", tags=["approvals"])
async def create_approval(payload: ApprovalPayload):
    """Creates a new pending human approval request."""
    with db_manager.SessionLocal() as session:
        record = ApprovalRecord(
            approval_id=payload.approval_id,
            incident_id=payload.incident_id,
            patch_sql=payload.patch_sql,
            tool=payload.tool,
            reasoning=payload.reasoning,
            risk_level=payload.risk_level or "HIGH",
            status="PENDING"
        )
        session.add(record)
        session.commit()
    return {"status": "success", "approval_id": payload.approval_id}


@app.post("/api/approvals/{approval_id}/approve", tags=["approvals"])
async def approve_patch(approval_id: str, action: ApprovalAction):
    """Human approves a pending high-risk patch – triggers remediation."""
    with db_manager.SessionLocal() as session:
        record = session.query(ApprovalRecord).filter_by(approval_id=approval_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Approval not found")
        if record.status != "PENDING":
            raise HTTPException(status_code=409, detail=f"Approval already {record.status}")

        record.status = "APPROVED"
        record.comment = action.comment or ""
        record.resolved_at = datetime.utcnow()
        session.commit()

        # Signal the orchestrator via Valkey
        await _publish_event(INCIDENT_CHANNEL, "APPROVAL_GRANTED", "INFO", {
            "approval_id": approval_id,
            "incident_id": record.incident_id,
            "patch": record.patch_sql,
            "reasoning": record.reasoning,
            "tool": record.tool,
        })

    return {"status": "approved", "approval_id": approval_id}


@app.post("/api/approvals/{approval_id}/reject", tags=["approvals"])
async def reject_patch(approval_id: str, action: ApprovalAction):
    """Human rejects a pending high-risk patch – incident stays unresolved."""
    with db_manager.SessionLocal() as session:
        record = session.query(ApprovalRecord).filter_by(approval_id=approval_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Approval not found")
        if record.status != "PENDING":
            raise HTTPException(status_code=409, detail=f"Approval already {record.status}")

        record.status = "REJECTED"
        record.comment = action.comment or ""
        record.resolved_at = datetime.utcnow()
        session.commit()

        await _publish_event(INCIDENT_CHANNEL, "APPROVAL_REJECTED", "WARNING", {
            "approval_id": approval_id,
            "incident_id": record.incident_id,
        })

    return {"status": "rejected", "approval_id": approval_id}
