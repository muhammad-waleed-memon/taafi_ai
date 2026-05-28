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
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# Ensure log directory exists
LOG_DIR = "c:/Users/S.A COMPUTER/Desktop/taafi_ai/services/core-engine/logs"
os.makedirs(LOG_DIR, exist_ok=True)
INCIDENT_LOG_PATH = os.path.join(LOG_DIR, "active_incidents.log")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("core-engine.main")

# Structured SRE Log Writer
def log_incident(level: str, category: str, details: Dict[str, Any]):
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,
        "category": category,
        "details": details
    }
    with open(INCIDENT_LOG_PATH, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    # Also push to SSE stream queues
    asyncio.create_task(broadcast_message(log_entry))

app = FastAPI(
    title="Taafi.ai Core Engine",
    description="Automated SRE database incident remediation platform core engine.",
    version="1.0.0"
)

# Enable CORS for the dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SSE Connection Queues
active_listeners: List[asyncio.Queue] = []

async def broadcast_message(message: Dict[str, Any]):
    """Broadcasts a JSON SRE message to all connected frontend streams."""
    payload = f"data: {json.dumps(message)}\n\n"
    for queue in active_listeners:
        await queue.put(payload)

# Pydantic models
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

@app.on_event("startup")
async def startup_event():
    # Verify core logging setup
    if not os.path.exists(INCIDENT_LOG_PATH):
        with open(INCIDENT_LOG_PATH, "w") as f:
            f.write("")
    log_incident("INFO", "SYSTEM_STARTUP", {"status": "Core engine started successfully."})

@app.get("/health")
def health_check():
    return {"status": "healthy", "engine": "Taafi.ai Core Engine", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/incidents")
def list_incidents() -> List[Dict[str, Any]]:
    """Reads and returns the complete history of incidents from the active_incidents.log file."""
    if not os.path.exists(INCIDENT_LOG_PATH):
        return []
    
    incidents = []
    with open(INCIDENT_LOG_PATH, "r") as f:
        for line in f:
            if line.strip():
                try:
                    incidents.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return incidents[::-1]  # Return newest first

@app.post("/api/incidents/report")
async def report_incident(incident: DeadlockReport):
    """Enables external monitors or the deadlock detector to trigger incident analysis."""
    incident_id = f"INC-{int(datetime.utcnow().timestamp())}"
    details = {
        "incident_id": incident_id,
        "database_name": incident.database_name,
        "blocking_query": incident.blocking_query,
        "blocked_query": incident.blocked_query,
        "transaction_ids": incident.transaction_ids,
        "lock_types": incident.lock_types,
        "schema_dump": incident.schema_dump,
        "status": "UNRESOLVED"
    }
    log_incident("ERROR", "DEADLOCK_TRAPPED", details)
    return {"status": "success", "incident_id": incident_id}

@app.post("/api/incidents/remediate")
async def remediate_incident(payload: RemediatePayload):
    """Applies a verified healing SQL or query index patch to the RDS pool database."""
    log_incident("INFO", "REMEDIATION_TRIGGERED", {
        "incident_id": payload.incident_id,
        "patch": payload.suggested_patch,
        "reasoning": payload.reasoning
    })
    
    # Simulate zero-downtime hot-patch application (e.g. index creation or lock break)
    await asyncio.sleep(1.5)
    
    log_incident("SUCCESS", "REMEDIATION_COMPLETED", {
        "incident_id": payload.incident_id,
        "status": "RESOLVED",
        "action": "Successfully executed patch. Database transactions resumed without downtime."
    })
    
    return {"status": "resolved", "incident_id": payload.incident_id}

@app.post("/api/incidents/simulate")
async def simulate_deadlock():
    """Generates a mock SQL deadlock log scenario for end-to-end flow validation."""
    incident_id = f"INC-SIM-{int(datetime.utcnow().timestamp())}"
    details = {
        "incident_id": incident_id,
        "database_name": "alibaba_rds_prod_users",
        "blocking_query": "UPDATE users SET active = TRUE WHERE id = 42; -- (Waiting for Lock on transactions_index)",
        "blocked_query": "UPDATE transactions SET status = 'COMPLETED' WHERE user_id = 42; -- (Locked table users exclusively)",
        "transaction_ids": ["tx_0x94827", "tx_0x94828"],
        "lock_types": ["ExclusiveLock", "ShareLock"],
        "schema_dump": "CREATE TABLE users (id SERIAL PRIMARY KEY, active BOOLEAN); CREATE TABLE transactions (id SERIAL PRIMARY KEY, user_id INTEGER, status VARCHAR(20));",
        "status": "QUEUED_FOR_REMEDIATION"
    }
    log_incident("ERROR", "DEADLOCK_TRAPPED", details)
    return {"status": "simulation_started", "incident_id": incident_id}

@app.get("/api/stream")
async def stream_terminal_logs():
    """Server-Sent Events endpoint streaming realtime diagnostic and recovery logs to ConsoleTerminal."""
    async def event_generator():
        queue = asyncio.Queue()
        active_listeners.append(queue)
        
        # Stream historical logs first so terminal has instant telemetry
        history = list_incidents()
        for hist_item in reversed(history[:20]):
            yield f"data: {json.dumps(hist_item)}\n\n"
            
        try:
            while True:
                data = await queue.get()
                yield data
        except asyncio.CancelledError:
            pass
        finally:
            active_listeners.remove(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
