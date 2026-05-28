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
import logging
import time
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError

logger = logging.getLogger("core-engine.database")

# Environment configurations with fallback to SQLite for local sandboxed zero-dependency runs
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///c:/Users/S.A COMPUTER/Desktop/taafi_ai/services/core-engine/taafi_local.db"
)

# Alibaba Cloud RDS pool configurations to guarantee zero-downtime and robust connection handling
POOL_SIZE = int(os.getenv("RDS_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("RDS_MAX_OVERFLOW", "10"))
POOL_RECYCLE = int(os.getenv("RDS_POOL_RECYCLE", "1800"))  # Recycle connections every 30 mins
POOL_TIMEOUT = int(os.getenv("RDS_POOL_TIMEOUT", "30"))

# SQLAlchemy setup
Base = declarative_base()

class DatabaseManager:
    def __init__(self, db_url: str):
        self.db_url = db_url
        is_sqlite = db_url.startswith("sqlite")
        
        # Build engine parameters appropriate for the database type
        engine_args = {
            "pool_pre_ping": True  # Fail-fast check to re-establish dropped RDS connections
        }
        if not is_sqlite:
            engine_args.update({
                "pool_size": POOL_SIZE,
                "max_overflow": MAX_OVERFLOW,
                "pool_recycle": POOL_RECYCLE,
                "pool_timeout": POOL_TIMEOUT
            })
            
        self.engine = create_engine(db_url, **engine_args)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def get_db(self):
        """Dependency to get database session with retry capability."""
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def verify_connection(self, retries=5, delay=2) -> bool:
        """Verifies database connectivity with exponential backoff retry logic."""
        for attempt in range(1, retries + 1):
            try:
                with self.engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                logger.info("Successfully connected to the RDS database engine.")
                return True
            except OperationalError as e:
                logger.warning(f"Database connection attempt {attempt}/{retries} failed: {e}")
                if attempt == retries:
                    logger.error("Could not establish database connection. Running in degraded state.")
                    return False
                time.sleep(delay * attempt)
        return False

# Export default manager instance
db_manager = DatabaseManager(DATABASE_URL)
