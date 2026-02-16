"""
AI PM Framework - Database Utilities

データベース操作のユーティリティモジュール群。
"""

from .db import (
    get_connection,
    execute_query,
    execute_many,
    fetch_one,
    fetch_all,
    transaction,
)
from .validation import (
    validate_project_name,
    validate_order_id,
    validate_task_id,
    validate_status,
    ValidationError,
)
from .transition import (
    is_transition_allowed,
    get_allowed_transitions,
    TransitionError,
)

__all__ = [
    # Database
    "get_connection",
    "execute_query",
    "execute_many",
    "fetch_one",
    "fetch_all",
    "transaction",
    # Validation
    "validate_project_name",
    "validate_order_id",
    "validate_task_id",
    "validate_status",
    "ValidationError",
    # Transition
    "is_transition_allowed",
    "get_allowed_transitions",
    "TransitionError",
]
