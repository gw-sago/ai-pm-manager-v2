"""
AI PM Framework - Status Module

統合ステータス取得機能を提供する。
1回のPython起動・DB接続でプロジェクト・ORDER・タスクの全情報を一括取得し、
/aipmコマンドの高速化を実現する。

モード別ヘルパー関数:
- get_single_project_status(conn, project_id): 単一プロジェクト
- get_active_projects_status(conn): アクティブプロジェクト自動検出
- get_all_projects_status(conn): 全プロジェクト
"""

from .aipm_status import (
    get_unified_status,
    get_single_project_status,
    get_active_projects_status,
    get_all_projects_status,
    format_human_readable,
)
