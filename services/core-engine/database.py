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
import time
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, text, Column, String, DateTime, Text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError

logger = logging.getLogger("core-engine.database")

# ─── Environment Configuration ────────────────────────────────────────────────
# TAAFI_DB_URL accepts either:
#   sqlite:///./taafi_local.db        (local dev – default)
#   postgresql://user:pw@host/dbname  (production ACK)
DATABASE_URL = os.getenv("TAAFI_DB_URL", "sqlite:///./taafi_local.db")

POOL_SIZE = int(os.getenv("RDS_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("RDS_MAX_OVERFLOW", "10"))
POOL_RECYCLE = int(os.getenv("RDS_POOL_RECYCLE", "1800"))  # recycle every 30 min
POOL_TIMEOUT = int(os.getenv("RDS_POOL_TIMEOUT", "30"))

# ─── ORM Base ─────────────────────────────────────────────────────────────────
Base = declarative_base()


class IncidentRecord(Base):
    """Persistent record of every detected database incident."""
    __tablename__ = "incidents"

    incident_id = Column(String(64), primary_key=True)
    category = Column(String(64), nullable=False)
    level = Column(String(16), nullable=False, default="INFO")
    details = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "incident_id": self.incident_id,
            "category": self.category,
            "level": self.level,
            "details": json.loads(self.details),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ApprovalRecord(Base):
    """Human-in-the-loop approval gate for high-risk patches."""
    __tablename__ = "approvals"

    approval_id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), nullable=False)
    patch_sql = Column(Text, nullable=False)
    tool = Column(String(64), nullable=True)
    reasoning = Column(Text, nullable=True)
    risk_level = Column(String(16), nullable=False, default="HIGH")
    status = Column(String(16), nullable=False, default="PENDING")
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "approval_id": self.approval_id,
            "incident_id": self.incident_id,
            "patch_sql": self.patch_sql,
            "tool": self.tool,
            "reasoning": self.reasoning,
            "risk_level": self.risk_level,
            "status": self.status,
            "comment": self.comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


class PatchHistoryRecord(Base):
    """Historical record of applied patches and their outcomes for few-shot Qwen context."""
    __tablename__ = "patch_history"

    id = Column(String(64), primary_key=True)
    incident_id = Column(String(64), nullable=False)
    table_names = Column(Text, nullable=False)   # JSON list
    lock_types = Column(Text, nullable=False)    # JSON list
    patch_sql = Column(Text, nullable=False)
    tool = Column(String(64), nullable=True)
    outcome = Column(String(16), nullable=False)  # SUCCESS | FAILURE
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "incident_id": self.incident_id,
            "table_names": json.loads(self.table_names),
            "lock_types": json.loads(self.lock_types),
            "patch_sql": self.patch_sql,
            "tool": self.tool,
            "outcome": self.outcome,
        }


# ─── Database Manager ─────────────────────────────────────────────────────────
class DatabaseManager:
    def __init__(self, db_url: str):
        self.db_url = db_url
        is_sqlite = db_url.startswith("sqlite")

        engine_args: dict = {"pool_pre_ping": True}
        if not is_sqlite:
            engine_args.update({
                "pool_size": POOL_SIZE,
                "max_overflow": MAX_OVERFLOW,
                "pool_recycle": POOL_RECYCLE,
                "pool_timeout": POOL_TIMEOUT,
            })

        self.engine = create_engine(db_url, **engine_args)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def create_tables(self):
        """Create all ORM-managed tables if they do not exist."""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables verified/created.")

    def verify_connection(self, retries: int = 5, delay: int = 2) -> bool:
        """Verifies database connectivity with exponential-backoff retry."""
        for attempt in range(1, retries + 1):
            try:
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("Database connection OK.")
                return True
            except OperationalError as exc:
                logger.warning("DB connection attempt %d/%d failed: %s", attempt, retries, exc)
                if attempt == retries:
                    logger.error("Could not establish DB connection – running in degraded state.")
                    return False
                time.sleep(delay * attempt)
        return False


# ─── Singleton Export ─────────────────────────────────────────────────────────
db_manager = DatabaseManager(DATABASE_URL)
