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
import asyncio
import logging

import valkey.asyncio as aioredis

from compressor import ContextCompressor
from analyzer_agent import DeadlockAnalyzerAgent
from fixer_agent import DeadlockFixerAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("neural-orchestrator.main")

# ─── Environment Configuration ────────────────────────────────────────────────
VALKEY_URL = os.getenv("VALKEY_URL", "redis://valkey:6379")
CORE_ENGINE_URL = os.getenv("CORE_ENGINE_URL", "http://core-engine:8000")

INCIDENT_CHANNEL = "taafi:incidents"
REMEDIATION_CHANNEL = "taafi:remediation"

# Risk classification keywords
AUTO_APPROVE_TOOLS = {"create_index"}                          # always safe
ESCALATE_TOOLS = {"kill_query", "drop_table", "reorder_transaction"}  # human approval required


class AutopilotOrchestrator:
    def __init__(self):
        self.analyzer = DeadlockAnalyzerAgent()
        self.fixer = DeadlockFixerAgent()
        # Track incident IDs we have already dispatched to avoid double-processing
        self.processed_incidents: set = set()
        # Map approval_id → remediation context, awaiting human decision
        self.pending_approvals: dict = {}
        self.valkey: aioredis.Valkey = None

    # ─── Startup ──────────────────────────────────────────────────────────
    async def connect(self):
        self.valkey = aioredis.Valkey.from_url(VALKEY_URL, decode_responses=True)
        await self.valkey.ping()
        logger.info("Neural Orchestrator connected to Valkey at %s", VALKEY_URL)

    # ─── Main Loop ────────────────────────────────────────────────────────
    async def run(self):
        """Subscribe to Valkey channels and dispatch handlers for each message."""
        await self.connect()
        pubsub = self.valkey.pubsub()
        await pubsub.subscribe(INCIDENT_CHANNEL)
        logger.info("Subscribed to Valkey channel: %s", INCIDENT_CHANNEL)

        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                event = json.loads(message["data"])
            except json.JSONDecodeError:
                logger.warning("Received non-JSON message on channel – skipping.")
                continue

            category = event.get("category")

            if category == "DEADLOCK_TRAPPED":
                details = event.get("details", {})
                incident_id = details.get("incident_id")
                if incident_id and incident_id not in self.processed_incidents:
                    self.processed_incidents.add(incident_id)
                    asyncio.create_task(self.remediate_flow(event))

            elif category == "APPROVAL_GRANTED":
                details = event.get("details", {})
                approval_id = details.get("approval_id")
                asyncio.create_task(self.execute_approved_patch(event))

            elif category == "APPROVAL_REJECTED":
                details = event.get("details", {})
                approval_id = details.get("approval_id")
                incident_id = details.get("incident_id")
                logger.warning(
                    "Approval %s REJECTED by human operator – incident %s stays unresolved.",
                    approval_id, incident_id,
                )


    # ─── Remediation Flow ─────────────────────────────────────────────────
    async def remediate_flow(self, incident: dict):
        """
        Full autopilot pipeline:
        1. Compress context
        2. Retrieve few-shot similar incidents from Core Engine
        3. Analyze deadlock
        4. Ask Qwen for structured tool call
        5. Risk-classify: auto-approve safe tools, escalate destructive ones
        6. Apply or queue for human approval
        """
        import httpx
        details = incident.get("details", {})
        incident_id = details.get("incident_id")
        logger.info("🔄 Starting autopilot remediation for incident: %s", incident_id)

        # 1. Compress context
        compressed = ContextCompressor.compress_incident(incident)

        # 2. Retrieve similar past incidents (persistent memory)
        few_shot_examples = []
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{CORE_ENGINE_URL}/api/incidents/similar", params={
                    "table_names": ",".join(
                        t for t in [compressed.get("db", "")] if t
                    ),
                    "lock_types": ",".join(compressed.get("locks", [])),
                    "limit": 3,
                })
                if resp.status_code == 200:
                    few_shot_examples = resp.json()
        except Exception as exc:
            logger.warning("Could not fetch few-shot examples: %s", exc)

        # 3. Analyze
        analysis = await self.analyzer.analyze_incident(compressed)
        logger.info("Analysis: %s", analysis.get("analysis_narrative", ""))

        # 4. Generate structured Qwen patch
        fixer_result = await self.fixer.generate_patch_via_qwen(
            compressed, analysis, few_shot_examples
        )
        tool_name = fixer_result.get("tool", "create_index")
        parameters = fixer_result.get("parameters", {})
        reasoning = fixer_result.get("reasoning", "")
        patch_sql = parameters.get("sql", "")

        logger.info("Qwen selected tool '%s': %s", tool_name, patch_sql)

        # Publish REMEDIATION_TRIGGERED so the web dashboard console displays it in real time
        from datetime import datetime
        if self.valkey:
            await self.valkey.publish(
                REMEDIATION_CHANNEL,
                json.dumps({
                    "timestamp": datetime.utcnow().isoformat(),
                    "level": "INFO",
                    "category": "REMEDIATION_TRIGGERED",
                    "details": {
                        "incident_id": incident_id,
                        "patch": patch_sql,
                        "reasoning": reasoning,
                        "tool": tool_name
                    }
                })
            )

        # 5. Sandbox validation
        sandbox_ok = await self.fixer.execute_in_sandbox(
            compressed.get("schema", ""), patch_sql
        )
        if not sandbox_ok:
            logger.error("Sandbox validation FAILED – aborting remediation for %s", incident_id)
            return

        # 6. Risk classification
        if tool_name in AUTO_APPROVE_TOOLS:
            logger.info("Tool '%s' auto-approved – applying immediately.", tool_name)
            await self._apply_patch(incident_id, patch_sql, reasoning, tool_name)
        else:
            logger.warning(
                "Tool '%s' is HIGH-RISK – escalating to human approval queue.", tool_name
            )
            await self._create_approval_request(
                incident_id, patch_sql, tool_name, parameters, reasoning
            )

    # ─── Execute Approved Patch ───────────────────────────────────────────
    async def execute_approved_patch(self, event: dict):
        """Called when a human approves a previously queued patch."""
        import httpx
        details = event.get("details", event)
        incident_id = details.get("incident_id")
        patch = details.get("patch", "")
        reasoning = details.get("reasoning", "")
        tool = details.get("tool", "")
        approval_id = details.get("approval_id")

        logger.info("✅ Human approved patch for incident %s (approval %s)", incident_id, approval_id)
        await self._apply_patch(incident_id, patch, reasoning, tool)

    # ─── Internal Helpers ─────────────────────────────────────────────────
    async def _apply_patch(self, incident_id: str, patch_sql: str, reasoning: str, tool: str):
        """POST the verified patch to the Core Engine for DB execution."""
        import httpx
        payload = {
            "incident_id": incident_id,
            "suggested_patch": patch_sql,
            "reasoning": reasoning,
            "tool": tool,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{CORE_ENGINE_URL}/api/incidents/remediate", json=payload
                )
                if resp.status_code == 200:
                    logger.info("✅ Incident %s resolved successfully.", incident_id)
                else:
                    logger.error("Remediation API error %d: %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.error("Error calling Core Engine remediation API: %s", exc)

    async def _create_approval_request(
        self,
        incident_id: str,
        patch_sql: str,
        tool: str,
        parameters: dict,
        reasoning: str,
    ):
        """Persist an approval request in the Core Engine and publish to Valkey for the dashboard."""
        import httpx
        approval_id = f"APR-{uuid.uuid4().hex[:8].upper()}"
        payload = {
            "approval_id": approval_id,
            "incident_id": incident_id,
            "patch_sql": patch_sql,
            "tool": tool,
            "parameters": parameters,
            "reasoning": reasoning,
            "risk_level": "HIGH",
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    f"{CORE_ENGINE_URL}/api/approvals", json=payload
                )
                if resp.status_code in (200, 201):
                    logger.info("Approval request %s created for incident %s", approval_id, incident_id)
                else:
                    logger.error(
                        "Could not create approval record: %d %s", resp.status_code, resp.text
                    )
        except Exception as exc:
            logger.error("Error posting approval request: %s", exc)

        # Also publish to Valkey so dashboard shows the pending approval immediately
        if self.valkey:
            await self.valkey.publish(
                INCIDENT_CHANNEL,
                json.dumps({
                    "category": "APPROVAL_REQUESTED",
                    **payload,
                }),
            )


# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    orchestrator = AutopilotOrchestrator()
    asyncio.run(orchestrator.run())
