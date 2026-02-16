"""
AI PM Framework - Configuration Module

Provides configuration management for the AI PM Framework.
Consolidates db_config (formerly config.py) and worker_config.
"""

from .db_config import (
    setup_utf8_output,
    DBConfig,
    AI_PM_ROOT,
    get_db_config,
    set_db_config,
    get_db_path,
    get_schema_path,
    get_data_dir,
    get_backup_dir,
    get_test_db_config,
    get_memory_db_config,
    ensure_data_dir,
    ensure_backup_dir,
    get_project_paths,
)

from .worker_config import (
    WorkerResourceConfig,
    WorkerPriorityConfig,
    get_worker_config,
    set_worker_config,
    get_priority_config,
    set_priority_config,
    load_config_from_env,
    get_recommended_max_workers,
)

from .permission_profiles import (
    load_profiles,
    get_profile,
    get_profile_tools,
    get_default_profile,
    list_profiles,
    validate_profile,
    get_profile_description,
    validate_all_profiles,
)

__all__ = [
    # db_config
    "setup_utf8_output",
    "DBConfig",
    "AI_PM_ROOT",
    "get_db_config",
    "set_db_config",
    "get_db_path",
    "get_schema_path",
    "get_data_dir",
    "get_backup_dir",
    "get_test_db_config",
    "get_memory_db_config",
    "ensure_data_dir",
    "ensure_backup_dir",
    "get_project_paths",
    # worker_config
    "WorkerResourceConfig",
    "WorkerPriorityConfig",
    "get_worker_config",
    "set_worker_config",
    "get_priority_config",
    "set_priority_config",
    "load_config_from_env",
    "get_recommended_max_workers",
    # permission_profiles
    "load_profiles",
    "get_profile",
    "get_profile_tools",
    "get_default_profile",
    "list_profiles",
    "validate_profile",
    "get_profile_description",
    "validate_all_profiles",
]
