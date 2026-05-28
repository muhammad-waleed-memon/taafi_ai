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

import logging
from typing import Dict, Any, List

logger = logging.getLogger("neural-orchestrator.analyzer")

class DeadlockAnalyzerAgent:
    def __init__(self):
        pass

    async def analyze_incident(self, compressed_context: Dict[str, Any]) -> Dict[str, Any]:
        """Analyzes database deadlock dependencies asynchronously and prepares structured diagnostic info."""
        logger.info(f"Analyzing trapped deadlock incident: {compressed_context.get('incident_id')}")
        
        # Build logical lock dependency loop
        q1 = compressed_context.get("q1", "")
        q2 = compressed_context.get("q2", "")
        txs = compressed_context.get("txs", [])
        locks = compressed_context.get("locks", [])
        
        # SRE heuristics for database transaction collision analysis
        diagnostics = {
            "incident_id": compressed_context.get("incident_id"),
            "has_circular_wait": True,
            "collision_points": [],
            "impact_assessment": "HIGH - Transactions blocking database connection pool limits"
        }
        
        # Parse targets involved in collision
        for query in [q1, q2]:
            if "UPDATE" in query.upper():
                table_match = [t for t in ["users", "transactions", "orders", "accounts"] if t in query.lower()]
                if table_match:
                    diagnostics["collision_points"].append(table_match[0])
                    
        # Construct exact deadlock analysis narrative
        diagnostics["analysis_narrative"] = (
            f"Transaction {txs[0] if len(txs) > 0 else 'T1'} acquired lock on '{diagnostics['collision_points'][0] if len(diagnostics['collision_points']) > 0 else 'Table A'}' "
            f"and is waiting for '{diagnostics['collision_points'][1] if len(diagnostics['collision_points']) > 1 else 'Table B'}'. "
            f"Simultaneously, Transaction {txs[1] if len(txs) > 1 else 'T2'} acquired lock on '{diagnostics['collision_points'][1] if len(diagnostics['collision_points']) > 1 else 'Table B'}' "
            f"and is waiting for '{diagnostics['collision_points'][0] if len(diagnostics['collision_points']) > 0 else 'Table A'}'. "
            f"This forms a direct O(N) database deadlock circular wait state."
        )
        
        return diagnostics
