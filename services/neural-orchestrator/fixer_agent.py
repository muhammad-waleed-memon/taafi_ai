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
import sqlite3
from typing import Dict, Any, Tuple, List, Optional

import httpx

logger = logging.getLogger("neural-orchestrator.fixer")

# ─── Qwen Tool Schema ─────────────────────────────────────────────────────────
# These are the tools Qwen may select. Each has a JSON schema of its parameters.
QWEN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_index",
            "description": (
                "Create a database index to eliminate full-table scans and resolve "
                "lock contention caused by missing indexes. Safe for zero-downtime deployment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The CREATE INDEX IF NOT EXISTS … SQL statement.",
                    },
                    "target_table": {"type": "string"},
                    "target_column": {"type": "string"},
                },
                "required": ["sql", "target_table", "target_column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "kill_query",
            "description": (
                "Terminate a long-running or blocking database query by its PID. "
                "HIGH RISK – requires human approval before execution."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "The SELECT pg_terminate_backend(pid) SQL statement.",
                    },
                    "pid": {"type": "integer", "description": "Process ID to terminate."},
                },
                "required": ["sql", "pid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reorder_transaction",
            "description": (
                "Reorder transaction locking order to break a circular deadlock wait chain. "
                "HIGH RISK – requires human approval before execution."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "Advisory lock acquisition SQL to enforce lock ordering.",
                    },
                    "lock_order": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered list of tables to acquire locks on.",
                    },
                },
                "required": ["sql", "lock_order"],
            },
        },
    },
]


class DeadlockFixerAgent:
    def __init__(self):
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.api_url = os.getenv(
            "QWEN_API_URL",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        )
        self.model = os.getenv("QWEN_MODEL_NAME", "qwen-max")

    async def generate_patch_via_qwen(
        self,
        compressed_context: Dict[str, Any],
        analysis: Dict[str, Any],
        few_shot_examples: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Calls the Qwen LLM with Structured Tool Calling.

        Returns a dict:
        {
            "tool":       "<tool_name>",
            "parameters": { ... },
            "reasoning":  "<explanation>"
        }
        """
        system_prompt = (
            "You are an expert SRE and Database Performance Architect. "
            "Analyse the deadlock context and call the most appropriate tool to resolve it. "
            "Use create_index for missing-index contention (zero-downtime). "
            "Use kill_query only when a blocking PID must be terminated. "
            "Use reorder_transaction to fix circular lock-ordering issues. "
            "Always choose the least-destructive option first."
        )

        # Inject few-shot examples into the user prompt
        few_shot_section = ""
        if few_shot_examples:
            few_shot_section = "\n\nSimilar Past Incidents (few-shot reference):\n"
            for ex in few_shot_examples[:3]:
                few_shot_section += (
                    f"- Incident {ex.get('incident_id')}: "
                    f"tables={ex.get('table_names')}, "
                    f"tool={ex.get('tool')}, "
                    f"patch={ex.get('patch_sql')}, "
                    f"outcome={ex.get('outcome')}\n"
                )

        user_prompt = (
            f"Deadlock Context:\n{json.dumps(compressed_context, indent=2)}\n\n"
            f"Incident Analysis:\n{json.dumps(analysis, indent=2)}"
            f"{few_shot_section}"
        )

        if not self.api_key:
            logger.warning("No DASHSCOPE_API_KEY – running deterministic fallback SRE engine.")
            return self._local_expert_remediation(compressed_context)

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "tools": QWEN_TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0.1,
                }

                response = await client.post(self.api_url, headers=headers, json=payload)

                if response.status_code == 200:
                    result = response.json()
                    choice = result["choices"][0]["message"]

                    # ── Structured tool call response ──────────────────
                    if choice.get("tool_calls"):
                        tool_call = choice["tool_calls"][0]
                        tool_name = tool_call["function"]["name"]
                        parameters = json.loads(tool_call["function"]["arguments"])
                        reasoning = choice.get("content") or f"Qwen selected tool: {tool_name}"
                        return {
                            "tool": tool_name,
                            "parameters": parameters,
                            "reasoning": reasoning,
                        }

                    # ── Fallback: plain-text JSON in content ───────────
                    content = choice.get("content", "")
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    try:
                        parsed = json.loads(content)
                        return {
                            "tool": parsed.get("tool", "create_index"),
                            "parameters": parsed.get("parameters", {"sql": parsed.get("patch_sql", "")}),
                            "reasoning": parsed.get("reasoning", ""),
                        }
                    except json.JSONDecodeError:
                        pass

                logger.error("Qwen API error %d: %s", response.status_code, response.text)
                return self._local_expert_remediation(compressed_context)

        except Exception as exc:
            logger.error("Error communicating with Qwen API: %s", exc)
            return self._local_expert_remediation(compressed_context)

    def _local_expert_remediation(self, compressed_context: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic fallback SRE rule engine used when Qwen is unavailable."""
        q1 = compressed_context.get("q1", "").lower()
        q2 = compressed_context.get("q2", "").lower()

        if "users" in q1 and "transactions" in q2:
            sql = "CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions (user_id);"
            reasoning = (
                "Detected circular lock wait between users and transactions tables. "
                "Adding an index on transactions(user_id) eliminates full-table scans, "
                "reducing transaction duration to <2 ms and resolving lock contention."
            )
            target_table, target_column = "transactions", "user_id"
        else:
            sql = "CREATE INDEX IF NOT EXISTS idx_users_active ON users (active);"
            reasoning = "Generic index alignment to prevent table-locking cascades under concurrent updates."
            target_table, target_column = "users", "active"

        return {
            "tool": "create_index",
            "parameters": {"sql": sql, "target_table": target_table, "target_column": target_column},
            "reasoning": reasoning,
        }

    async def execute_in_sandbox(self, schema_ddl: str, patch_sql: str) -> bool:
        """Validates the patch in an isolated in-memory SQLite sandbox before production execution."""
        logger.info("Initialising SQLite validation sandbox…")
        try:
            conn = sqlite3.connect(":memory:")
            cursor = conn.cursor()

            if schema_ddl:
                for stmt in [s.strip() for s in schema_ddl.split(";") if s.strip()]:
                    cursor.execute(stmt)

            for stmt in [s.strip() for s in patch_sql.split(";") if s.strip()]:
                cursor.execute(stmt)

            conn.commit()
            conn.close()
            logger.info("Sandbox validation PASSED.")
            return True
        except Exception as exc:
            logger.error("Sandbox validation FAILED: %s", exc)
            return False
