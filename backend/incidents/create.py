#!/usr/bin/env python3
import logging
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, execute_query

logger = logging.getLogger(__name__)

class IncidentCategory(Enum):
    WORKER_FAILURE = "WORKER_FAILURE"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    OTHER = "OTHER"
    
class IncidentSeverity(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

def create_incident(
    project_id: str,
    task_id: Optional[str],
    category: str,
    description: str,
    root_cause: Optional[str] = None,
    severity: str = "MEDIUM",
    order_id: Optional[str] = None,
    affected_records: Optional[str] = None,
    verbose: bool = False
) -> str:
    timestamp = datetime.now().isoformat()
    incident_id = f"INC_{timestamp.replace(':', '').replace('-', '').replace('.', '_')}"
    
    conn = get_connection()
    try:
        execute_query(
            conn,
            """INSERT INTO incidents 
               (incident_id, timestamp, project_id, order_id, task_id, category, severity, description, root_cause, affected_records)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (incident_id, timestamp, project_id, order_id, task_id, category, severity, description, root_cause, affected_records)
        )
        conn.commit()
        logger.info(f"Incident created: {incident_id}")
        return incident_id
    finally:
        conn.close()
