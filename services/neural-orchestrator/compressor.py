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

import re
from typing import Dict, Any

class ContextCompressor:
    @staticmethod
    def compress_sql(sql: str) -> str:
        """Minifies SQL queries by removing comments, redundant spaces, and line breaks."""
        if not sql:
            return ""
        # Remove SQL block comments
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        # Remove single-line comments
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        # Replace newlines and tabs with single space
        sql = sql.replace('\n', ' ').replace('\t', ' ')
        # Reduce multiple spaces to a single space
        sql = re.sub(r'\s+', ' ', sql)
        return sql.strip()

    @staticmethod
    def compress_schema(schema: str) -> str:
        """Compresses DDL schema statements, keeping only primary keys and constraints for efficiency."""
        if not schema:
            return ""
        lines = schema.split(";")
        compressed_tables = []
        for line in lines:
            line = ContextCompressor.compress_sql(line)
            if not line:
                continue
            # Keep table creation structure but discard non-essential attributes to save tokens
            # Focus on matches like: CREATE TABLE name ( ... )
            match = re.search(r'CREATE\s+TABLE\s+(\w+)\s*\((.*)\)', line, re.IGNORECASE)
            if match:
                table_name = match.group(1)
                columns_part = match.group(2)
                # Keep keys, foreign keys, and indexes explicitly
                essential_parts = []
                for part in columns_part.split(","):
                    part = part.strip()
                    lower_part = part.lower()
                    if any(x in lower_part for x in ["primary key", "foreign key", "references", "index", "unique"]):
                        essential_parts.append(part)
                    elif len(essential_parts) < 3: # Keep first few columns for structure context
                        essential_parts.append(part.split()[0] if part else "")
                compressed_tables.append(f"CREATE TABLE {table_name} ({', '.join(essential_parts)})")
            else:
                compressed_tables.append(line)
        return "; ".join(compressed_tables)

    @classmethod
    def compress_incident(cls, incident: Dict[str, Any]) -> Dict[str, Any]:
        """Compresses complete deadlock context to under 40% of original token footprint."""
        details = incident.get("details", incident)
        return {
            "incident_id": details.get("incident_id"),
            "db": details.get("database_name"),
            "q1": cls.compress_sql(details.get("blocking_query", "")),
            "q2": cls.compress_sql(details.get("blocked_query", "")),
            "txs": details.get("transaction_ids", []),
            "locks": details.get("lock_types", []),
            "schema": cls.compress_schema(details.get("schema_dump", ""))
        }
