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
import asyncio
import logging
import httpx
from compressor import ContextCompressor
from analyzer_agent import DeadlockAnalyzerAgent
from fixer_agent import DeadlockFixerAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("neural-orchestrator.main")

INCIDENT_LOG_PATH = "c:/Users/S.A COMPUTER/Desktop/taafi_ai/services/core-engine/logs/active_incidents.log"
CORE_ENGINE_URL = os.getenv("CORE_ENGINE_URL", "http://localhost:8000")

class AutopilotOrchestrator:
    def __init__(self):
        self.analyzer = DeadlockAnalyzerAgent()
        self.fixer = DeadlockFixerAgent()
        self.processed_incidents = set()

    async def poll_active_incidents(self):
        """Polls the active incidents file for new deadlocks requiring self-healing remediation."""
        logger.info("Autopilot Orchestrator started. Watching active_incidents.log...")
        
        while True:
            try:
                if os.path.exists(INCIDENT_LOG_PATH):
                    with open(INCIDENT_LOG_PATH, "r") as f:
                        lines = f.readlines()
                    
                    for line in lines:
                        if not line.strip():
                            continue
                        
                        incident_data = json.loads(line)
                        details = incident_data.get("details", {})
                        incident_id = details.get("incident_id")
                        category = incident_data.get("category")
                        
                        # Process only unresolved deadlock incidents we haven't handled yet
                        if category == "DEADLOCK_TRAPPED" and incident_id not in self.processed_incidents:
                            self.processed_incidents.add(incident_id)
                            asyncio.create_task(self.remediate_flow(incident_data))
                            
            except Exception as e:
                logger.error(f"Error during incident log polling: {e}")
                
            await asyncio.sleep(2.0)

    async def remediate_flow(self, incident: dict):
        """Orchestrates the end-to-end trapping, analysis, Qwen patching, sandboxing, and execution."""
        details = incident.get("details", {})
        incident_id = details.get("incident_id")
        
        logger.info(f"🔄 Starting autopilot remediation flow for incident: {incident_id}")
        
        # 1. Compress Transaction Context
        compressed = ContextCompressor.compress_incident(incident)
        logger.info(f"Compressed transaction logs context. Reduced DDL schemas token volume.")
        
        # 2. Analyze Lock Conflicts
        analysis = await self.analyzer.analyze_incident(compressed)
        logger.info(f"Deadlock collision analysis narrative built: {analysis['analysis_narrative']}")
        
        # 3. Request Healing Patch from Qwen
        patch_sql, reasoning = await self.fixer.generate_patch_via_qwen(compressed, analysis)
        logger.info(f"Healing SQL patch generated: {patch_sql}")
        
        # 4. Dry-run Sandbox Validation
        sandbox_ok = await self.fixer.execute_in_sandbox(compressed.get("schema", ""), patch_sql)
        
        if sandbox_ok:
            logger.info("Sandbox dry-run successful. Applying hot-patch to production RDS pool...")
            
            # 5. Apply SQL Remediation Patch
            async with httpx.AsyncClient() as client:
                try:
                    payload = {
                        "incident_id": incident_id,
                        "suggested_patch": patch_sql,
                        "reasoning": reasoning
                    }
                    response = await client.post(f"{CORE_ENGINE_URL}/api/incidents/remediate", json=payload)
                    if response.status_code == 200:
                        logger.info(f"Successfully remediated incident: {incident_id}")
                    else:
                        logger.error(f"Failed to post remediation: {response.text}")
                except Exception as e:
                    logger.error(f"Error calling remediation API: {e}")
        else:
            logger.error(f"Sandbox check failed. Autopilot aborted remediation to prevent zero-downtime degradation.")

if __name__ == "__main__":
    orchestrator = AutopilotOrchestrator()
    asyncio.run(orchestrator.poll_active_incidents())
