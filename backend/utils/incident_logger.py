"""
AI PM Framework - Incident Logger Utility

Manages incident tracking and recording for failure pattern analysis.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from utils.db import (
    get_connection, execute_query, fetch_one, fetch_all,
    row_to_dict, rows_to_dicts, DatabaseError, transaction
)


class IncidentLoggerError(Exception):
    """Incident logger operation error"""
    pass


class IncidentLogger:
    """Manages incident tracking and recording"""

    # Valid categories
    CATEGORIES = [
        'MIGRATION_ERROR',
        'CASCADE_DELETE',
        'CONSTRAINT_VIOLATION',
        'DATA_INTEGRITY',
        'CONCURRENCY_ERROR',
        'FILE_LOCK_ERROR',
        'WORKER_FAILURE',
        'REVIEW_ERROR',
        'SYSTEM_ERROR',
        'OTHER'
    ]

    # Valid severity levels
    SEVERITIES = ['HIGH', 'MEDIUM', 'LOW']

    @staticmethod
    def generate_incident_id() -> str:
        """
        Generate a new incident ID

        Returns:
            str: Generated incident ID (e.g., INC_001)
        """
        conn = get_connection()
        try:
            # Find the highest numeric incident ID
            row = fetch_one(
                conn,
                "SELECT incident_id FROM incidents WHERE incident_id LIKE 'INC_%' ORDER BY incident_id DESC LIMIT 1"
            )

            if row is None:
                return "INC_001"

            last_id = row["incident_id"]
            try:
                # Extract number from INC_XXX format
                num = int(last_id.split("_")[1])
                return f"INC_{num + 1:03d}"
            except (ValueError, IndexError):
                # If parsing fails, default to INC_001
                return "INC_001"

        finally:
            conn.close()

    @staticmethod
    def create_incident(
        category: str,
        description: str,
        severity: str = 'MEDIUM',
        project_id: Optional[str] = None,
        order_id: Optional[str] = None,
        task_id: Optional[str] = None,
        root_cause: Optional[str] = None,
        resolution: Optional[str] = None,
        affected_records: Optional[List[str]] = None
    ) -> str:
        """
        Create a new incident record

        Args:
            category: Incident category (must be one of CATEGORIES)
            description: Incident description
            severity: Severity level (HIGH/MEDIUM/LOW)
            project_id: Related project ID (optional)
            order_id: Related ORDER ID (optional)
            task_id: Related task ID (optional)
            root_cause: Root cause analysis (optional)
            resolution: Resolution details (optional)
            affected_records: List of affected record IDs (optional)

        Returns:
            str: Created incident ID

        Raises:
            IncidentLoggerError: If incident creation fails
        """
        # Validate category
        if category not in IncidentLogger.CATEGORIES:
            raise IncidentLoggerError(
                f"Invalid category: {category}. Must be one of {IncidentLogger.CATEGORIES}"
            )

        # Validate severity
        if severity not in IncidentLogger.SEVERITIES:
            raise IncidentLoggerError(
                f"Invalid severity: {severity}. Must be one of {IncidentLogger.SEVERITIES}"
            )

        incident_id = IncidentLogger.generate_incident_id()
        now = datetime.now().isoformat()

        # Convert affected_records to JSON string
        affected_records_json = None
        if affected_records:
            affected_records_json = json.dumps(affected_records)

        with transaction() as conn:
            try:
                execute_query(
                    conn,
                    """
                    INSERT INTO incidents (
                        incident_id, timestamp, project_id, order_id, task_id,
                        category, severity, description, root_cause, resolution,
                        affected_records, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        incident_id, now, project_id, order_id, task_id,
                        category, severity, description, root_cause, resolution,
                        affected_records_json, now
                    )
                )

                return incident_id

            except DatabaseError as e:
                raise IncidentLoggerError(f"Failed to create incident: {e}")

    @staticmethod
    def update_incident(
        incident_id: str,
        root_cause: Optional[str] = None,
        resolution: Optional[str] = None
    ) -> bool:
        """
        Update incident with root cause or resolution

        Args:
            incident_id: Incident ID to update
            root_cause: Root cause analysis (optional)
            resolution: Resolution details (optional)

        Returns:
            bool: True if updated successfully

        Raises:
            IncidentLoggerError: If update fails
        """
        if root_cause is None and resolution is None:
            raise IncidentLoggerError("Must provide at least one of root_cause or resolution")

        with transaction() as conn:
            try:
                # Build update query dynamically
                updates = []
                params = []

                if root_cause is not None:
                    updates.append("root_cause = ?")
                    params.append(root_cause)

                if resolution is not None:
                    updates.append("resolution = ?")
                    params.append(resolution)

                params.append(incident_id)

                query = f"UPDATE incidents SET {', '.join(updates)} WHERE incident_id = ?"
                execute_query(conn, query, tuple(params))

                return True

            except DatabaseError as e:
                raise IncidentLoggerError(f"Failed to update incident: {e}")

    @staticmethod
    def get_incident(incident_id: str) -> Optional[Dict[str, Any]]:
        """
        Get incident by ID

        Args:
            incident_id: Incident ID

        Returns:
            Dict or None: Incident data or None if not found
        """
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                "SELECT * FROM incidents WHERE incident_id = ?",
                (incident_id,)
            )

            if row is None:
                return None

            incident = row_to_dict(row)

            # Parse affected_records JSON
            if incident and incident.get('affected_records'):
                incident['affected_records'] = json.loads(incident['affected_records'])

            return incident

        finally:
            conn.close()

    @staticmethod
    def get_incidents_by_category(
        category: str,
        limit: Optional[int] = None,
        project_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get incidents by category

        Args:
            category: Incident category
            limit: Maximum number of incidents to return (optional)
            project_id: Filter by project ID (optional)

        Returns:
            List[Dict]: List of incidents
        """
        conn = get_connection()
        try:
            query = "SELECT * FROM incidents WHERE category = ?"
            params = [category]

            if project_id:
                query += " AND project_id = ?"
                params.append(project_id)

            query += " ORDER BY timestamp DESC"

            if limit:
                query += f" LIMIT {limit}"

            rows = fetch_all(conn, query, tuple(params))
            incidents = rows_to_dicts(rows)

            # Parse affected_records JSON
            for incident in incidents:
                if incident.get('affected_records'):
                    incident['affected_records'] = json.loads(incident['affected_records'])

            return incidents

        finally:
            conn.close()

    @staticmethod
    def get_incidents_by_severity(
        severity: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get incidents by severity

        Args:
            severity: Severity level (HIGH/MEDIUM/LOW)
            limit: Maximum number of incidents to return (optional)

        Returns:
            List[Dict]: List of incidents
        """
        conn = get_connection()
        try:
            query = "SELECT * FROM incidents WHERE severity = ? ORDER BY timestamp DESC"

            if limit:
                query += f" LIMIT {limit}"

            rows = fetch_all(conn, query, (severity,))
            incidents = rows_to_dicts(rows)

            # Parse affected_records JSON
            for incident in incidents:
                if incident.get('affected_records'):
                    incident['affected_records'] = json.loads(incident['affected_records'])

            return incidents

        finally:
            conn.close()

    @staticmethod
    def get_incidents_by_project(
        project_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get incidents by project

        Args:
            project_id: Project ID
            limit: Maximum number of incidents to return (optional)

        Returns:
            List[Dict]: List of incidents
        """
        conn = get_connection()
        try:
            query = "SELECT * FROM incidents WHERE project_id = ? ORDER BY timestamp DESC"

            if limit:
                query += f" LIMIT {limit}"

            rows = fetch_all(conn, query, (project_id,))
            incidents = rows_to_dicts(rows)

            # Parse affected_records JSON
            for incident in incidents:
                if incident.get('affected_records'):
                    incident['affected_records'] = json.loads(incident['affected_records'])

            return incidents

        finally:
            conn.close()

    @staticmethod
    def get_incidents_by_order(
        order_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get incidents by ORDER

        Args:
            order_id: ORDER ID
            limit: Maximum number of incidents to return (optional)

        Returns:
            List[Dict]: List of incidents
        """
        conn = get_connection()
        try:
            query = "SELECT * FROM incidents WHERE order_id = ? ORDER BY timestamp DESC"

            if limit:
                query += f" LIMIT {limit}"

            rows = fetch_all(conn, query, (order_id,))
            incidents = rows_to_dicts(rows)

            # Parse affected_records JSON
            for incident in incidents:
                if incident.get('affected_records'):
                    incident['affected_records'] = json.loads(incident['affected_records'])

            return incidents

        finally:
            conn.close()

    @staticmethod
    def get_incidents_by_task(
        task_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get incidents by task

        Args:
            task_id: Task ID
            limit: Maximum number of incidents to return (optional)

        Returns:
            List[Dict]: List of incidents
        """
        conn = get_connection()
        try:
            query = "SELECT * FROM incidents WHERE task_id = ? ORDER BY timestamp DESC"

            if limit:
                query += f" LIMIT {limit}"

            rows = fetch_all(conn, query, (task_id,))
            incidents = rows_to_dicts(rows)

            # Parse affected_records JSON
            for incident in incidents:
                if incident.get('affected_records'):
                    incident['affected_records'] = json.loads(incident['affected_records'])

            return incidents

        finally:
            conn.close()

    @staticmethod
    def get_incidents_summary(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get incident summary statistics

        Args:
            start_date: Start date for filtering (ISO format, optional)
            end_date: End date for filtering (ISO format, optional)
            project_id: Filter by project ID (optional)

        Returns:
            Dict: Summary statistics including:
                - total: Total incident count
                - by_category: Count by category
                - by_severity: Count by severity
                - recent_high: Recent high severity incidents
        """
        conn = get_connection()
        try:
            # Build WHERE clause
            where_clauses = []
            params = []

            if start_date:
                where_clauses.append("timestamp >= ?")
                params.append(start_date)

            if end_date:
                where_clauses.append("timestamp <= ?")
                params.append(end_date)

            if project_id:
                where_clauses.append("project_id = ?")
                params.append(project_id)

            where_sql = ""
            if where_clauses:
                where_sql = " WHERE " + " AND ".join(where_clauses)

            # Total count
            total_row = fetch_one(
                conn,
                f"SELECT COUNT(*) as count FROM incidents{where_sql}",
                tuple(params) if params else None
            )
            total = total_row["count"] if total_row else 0

            # By category
            category_rows = fetch_all(
                conn,
                f"""
                SELECT category, COUNT(*) as count
                FROM incidents{where_sql}
                GROUP BY category
                ORDER BY count DESC
                """,
                tuple(params) if params else None
            )
            by_category = {row["category"]: row["count"] for row in category_rows}

            # By severity
            severity_rows = fetch_all(
                conn,
                f"""
                SELECT severity, COUNT(*) as count
                FROM incidents{where_sql}
                GROUP BY severity
                ORDER BY count DESC
                """,
                tuple(params) if params else None
            )
            by_severity = {row["severity"]: row["count"] for row in severity_rows}

            # Recent high severity incidents
            high_severity_query = f"""
                SELECT * FROM incidents{where_sql}
                {' AND ' if where_sql else ' WHERE '}severity = 'HIGH'
                ORDER BY timestamp DESC
                LIMIT 10
            """
            high_rows = fetch_all(conn, high_severity_query, tuple(params) if params else None)
            recent_high = rows_to_dicts(high_rows)

            # Parse affected_records JSON
            for incident in recent_high:
                if incident.get('affected_records'):
                    incident['affected_records'] = json.loads(incident['affected_records'])

            return {
                'total': total,
                'by_category': by_category,
                'by_severity': by_severity,
                'recent_high': recent_high
            }

        finally:
            conn.close()

    @staticmethod
    def get_recurrence_rate(
        category: str,
        days: int = 30,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate recurrence rate for a specific category

        Args:
            category: Incident category
            days: Number of days to look back
            project_id: Filter by project ID (optional)

        Returns:
            Dict: Recurrence statistics including:
                - category: Category name
                - total_incidents: Total incidents in period
                - days_analyzed: Number of days analyzed
                - recurrence_rate: Incidents per day
                - trend: 'increasing', 'decreasing', or 'stable'
        """
        conn = get_connection()
        try:
            # Calculate start date
            from datetime import datetime, timedelta
            start_date = (datetime.now() - timedelta(days=days)).isoformat()

            # Build WHERE clause
            where_sql = "WHERE category = ? AND timestamp >= ?"
            params = [category, start_date]

            if project_id:
                where_sql += " AND project_id = ?"
                params.append(project_id)

            # Total incidents in period
            total_row = fetch_one(
                conn,
                f"SELECT COUNT(*) as count FROM incidents {where_sql}",
                tuple(params)
            )
            total = total_row["count"] if total_row else 0

            # Calculate recurrence rate
            recurrence_rate = total / days if days > 0 else 0

            # Calculate trend (compare first half vs second half)
            mid_date = (datetime.now() - timedelta(days=days//2)).isoformat()

            first_half_row = fetch_one(
                conn,
                f"""
                SELECT COUNT(*) as count FROM incidents
                WHERE category = ? AND timestamp >= ? AND timestamp < ?
                {' AND project_id = ?' if project_id else ''}
                """,
                tuple([category, start_date, mid_date] + ([project_id] if project_id else []))
            )
            first_half = first_half_row["count"] if first_half_row else 0

            second_half_row = fetch_one(
                conn,
                f"""
                SELECT COUNT(*) as count FROM incidents
                WHERE category = ? AND timestamp >= ?
                {' AND project_id = ?' if project_id else ''}
                """,
                tuple([category, mid_date] + ([project_id] if project_id else []))
            )
            second_half = second_half_row["count"] if second_half_row else 0

            # Determine trend
            if second_half > first_half * 1.2:
                trend = 'increasing'
            elif second_half < first_half * 0.8:
                trend = 'decreasing'
            else:
                trend = 'stable'

            return {
                'category': category,
                'total_incidents': total,
                'days_analyzed': days,
                'recurrence_rate': round(recurrence_rate, 2),
                'first_half_count': first_half,
                'second_half_count': second_half,
                'trend': trend
            }

        finally:
            conn.close()


# Convenience function for quick incident logging
def log_incident(
    category: str,
    description: str,
    severity: str = 'MEDIUM',
    **kwargs
) -> str:
    """
    Convenience function to log an incident

    Args:
        category: Incident category
        description: Incident description
        severity: Severity level (default: MEDIUM)
        **kwargs: Additional arguments passed to create_incident

    Returns:
        str: Created incident ID
    """
    return IncidentLogger.create_incident(
        category=category,
        description=description,
        severity=severity,
        **kwargs
    )
