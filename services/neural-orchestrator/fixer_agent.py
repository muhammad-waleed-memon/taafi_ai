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
from typing import Dict, Any, Tuple
import httpx

logger = logging.getLogger("neural-orchestrator.fixer")

class DeadlockFixerAgent:
    def __init__(self):
        # DashScope/Qwen compatibility configurations using OpenAI standard endpoints
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.api_url = os.getenv("QWEN_API_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
        self.model = os.getenv("QWEN_MODEL_NAME", "qwen-max")

    async def generate_patch_via_qwen(self, compressed_context: Dict[str, Any], analysis: Dict[str, Any]) -> Tuple[str, str]:
        """Calls Alibaba Qwen LLM API to generate a precise database deadlock remediation patch."""
        system_prompt = (
            "You are an expert SRE and Database Performance Architect. Generate a zero-downtime database deadlock "
            "remediation patch (SQL index or order resequencing) based on the transaction analysis. "
            "Your output must be structured strictly in JSON format: "
            '{"patch_sql": "YOUR_SQL_QUERY_PATCH", "reasoning": "YOUR_SRE_EXPLANATION"}'
        )
        
        user_prompt = (
            f"Deadlock Context:\n{json.dumps(compressed_context, indent=2)}\n\n"
            f"Incident Analysis:\n{json.dumps(analysis, indent=2)}"
        )
        
        if not self.api_key:
            logger.warning("No DASHSCOPE_API_KEY detected. Running local fallback SRE rule engine.")
            return self._local_expert_remediation(compressed_context)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.1
                }
                
                response = await client.post(self.api_url, headers=headers, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    # Extract JSON if returned inside markdown blocks
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    parsed = json.loads(content)
                    return parsed["patch_sql"], parsed["reasoning"]
                else:
                    logger.error(f"Qwen API error {response.status_code}: {response.text}")
                    return self._local_expert_remediation(compressed_context)
        except Exception as e:
            logger.error(f"Error communicating with Qwen API: {e}")
            return self._local_expert_remediation(compressed_context)

    def _local_expert_remediation(self, compressed_context: Dict[str, Any]) -> Tuple[str, str]:
        """Deterministic fallback SRE expert system for local offline validation and test suites."""
        q1 = compressed_context.get("q1", "").lower()
        q2 = compressed_context.get("q2", "").lower()
        
        if "users" in q1 and "transactions" in q2:
            patch = "CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions (user_id);"
            reason = (
                "Trapped circular lock wait between users and transactions. "
                "Adding a high-performance index on transactions(user_id) eliminates full-table scans, "
                "compressing transaction duration to <2ms, resolving lock contention."
            )
        else:
            patch = "CREATE INDEX IF NOT EXISTS idx_remediation_target ON users (active);"
            reason = "Applying generic index lock alignment to avoid table locking cascades under concurrent updates."
            
        return patch, reason

    async def execute_in_sandbox(self, schema_ddl: str, patch_sql: str) -> bool:
        """Executes the proposed patch in a isolated sandboxed SQLite db to confirm compilation validity."""
        logger.info("Initializing isolated SQLite validation sandbox...")
        
        try:
            # Create an in-memory database representing the sandbox
            conn = sqlite3.connect(":memory:")
            cursor = conn.cursor()
            
            # 1. Recreate the schema environment
            if schema_ddl:
                statements = [s.strip() for s in schema_ddl.split(";") if s.strip()]
                for stmt in statements:
                    cursor.execute(stmt)
                    
            # 2. Apply patch to verify it compiles perfectly without errors
            statements = [s.strip() for s in patch_sql.split(";") if s.strip()]
            for stmt in statements:
                cursor.execute(stmt)
                
            conn.commit()
            conn.close()
            logger.info("Sandbox dry-run validation passed. Patch compiled successfully.")
            return True
        except Exception as e:
            logger.error(f"Sandbox verification failed for patch: {e}")
            return False
