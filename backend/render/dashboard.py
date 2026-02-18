"""
AI PM Framework - Dashboard Renderer

DBからDASHBOARD.mdを生成するレンダリング機能。
エグゼクティブダッシュボード（全体俯瞰）用のデータクラスとレンダリング機能を提供する。
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
except ImportError:
    print("Error: jinja2 is required. Install with: pip install jinja2", file=sys.stderr)
    sys.exit(1)


# パス設定
SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = SCRIPT_DIR / "templates"


class HealthStatus(Enum):
    """プロジェクト健康状態"""
    HEALTHY = "healthy"      # 正常
    WARNING = "warning"      # 注意
    CRITICAL = "critical"    # 危険
    UNKNOWN = "unknown"      # 不明


@dataclass
class ProjectHealthData:
    """
    プロジェクト健康状態データ

    プロジェクトの全体的な健康状態を表す。
    ORDER進捗、タスク完了率、エスカレーション状況、レビュー待ち数などから算出。
    """
    project_id: str
    project_name: str
    status: HealthStatus = HealthStatus.UNKNOWN

    # ORDER情報
    current_order_id: Optional[str] = None
    current_order_title: Optional[str] = None
    order_status: Optional[str] = None

    # 進捗指標
    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0
    blocked_tasks: int = 0
    rework_tasks: int = 0

    # 健康指標
    completion_rate: float = 0.0  # 完了率 (0.0-1.0)
    pending_reviews: int = 0       # レビュー待ち数
    open_escalations: int = 0      # 未解決エスカレーション数
    blocked_ratio: float = 0.0     # ブロック率 (0.0-1.0)

    # 最終更新
    last_activity: Optional[str] = None

    def calculate_status(self) -> HealthStatus:
        """
        健康状態を計算

        判定基準:
        - CRITICAL: エスカレーション未解決、またはブロック率50%以上
        - WARNING: ブロック率20%以上、または差戻しタスクあり、またはレビュー待ち5件以上
        - HEALTHY: 上記に該当しない
        - UNKNOWN: タスクがない
        """
        if self.total_tasks == 0:
            return HealthStatus.UNKNOWN

        # CRITICAL条件
        if self.open_escalations > 0:
            return HealthStatus.CRITICAL
        if self.blocked_ratio >= 0.5:
            return HealthStatus.CRITICAL

        # WARNING条件
        if self.blocked_ratio >= 0.2:
            return HealthStatus.WARNING
        if self.rework_tasks > 0:
            return HealthStatus.WARNING
        if self.pending_reviews >= 5:
            return HealthStatus.WARNING

        return HealthStatus.HEALTHY


@dataclass
class EscalationSummary:
    """
    エスカレーション集約データ

    プロジェクト横断でエスカレーション状況をサマリ表示するためのデータ。
    """
    total_open: int = 0              # 未解決エスカレーション総数
    total_resolved_today: int = 0    # 本日解決数
    oldest_open_days: int = 0        # 最も古い未解決エスカレーションの経過日数

    # プロジェクト別内訳
    by_project: Dict[str, int] = field(default_factory=dict)

    # 詳細リスト（直近5件）
    recent_escalations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """テンプレート用辞書に変換"""
        return {
            "total_open": self.total_open,
            "total_resolved_today": self.total_resolved_today,
            "oldest_open_days": self.oldest_open_days,
            "by_project": self.by_project,
            "recent_escalations": self.recent_escalations,
        }


@dataclass
class PendingReviewSummary:
    """
    承認待ち集約データ

    レビューキューの状況をサマリ表示するためのデータ。
    """
    total_pending: int = 0           # 承認待ち総数
    total_in_review: int = 0         # レビュー中総数
    p0_count: int = 0                # P0（最優先）件数
    p1_count: int = 0                # P1（通常）件数
    p2_count: int = 0                # P2（低優先）件数

    # プロジェクト別内訳
    by_project: Dict[str, int] = field(default_factory=dict)

    # 最も古い待ち時間（時間単位）
    oldest_pending_hours: float = 0.0

    # 詳細リスト（優先度順、直近10件）
    pending_items: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """テンプレート用辞書に変換"""
        return {
            "total_pending": self.total_pending,
            "total_in_review": self.total_in_review,
            "p0_count": self.p0_count,
            "p1_count": self.p1_count,
            "p2_count": self.p2_count,
            "by_project": self.by_project,
            "oldest_pending_hours": self.oldest_pending_hours,
            "pending_items": self.pending_items,
        }


@dataclass
class BacklogSummary:
    """
    バックログ集約データ

    BACKLOGの状況をサマリ表示するためのデータ。
    """
    total_items: int = 0             # 全項目数
    todo_count: int = 0              # TODO数
    in_progress_count: int = 0       # 進行中数
    high_priority_count: int = 0     # High優先度数

    # プロジェクト別内訳
    by_project: Dict[str, int] = field(default_factory=dict)

    # カテゴリ別内訳
    by_category: Dict[str, int] = field(default_factory=dict)

    # 直近追加項目（直近5件）
    recent_items: List[Dict[str, Any]] = field(default_factory=list)

    # 優先度別内訳
    by_priority: Dict[str, int] = field(default_factory=dict)

    # ステータス別内訳
    by_status: Dict[str, int] = field(default_factory=dict)

    # フィルタ結果（オプション）
    filtered_items: List[Dict[str, Any]] = field(default_factory=list)
    applied_filters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """テンプレート用辞書に変換"""
        return {
            "total_items": self.total_items,
            "todo_count": self.todo_count,
            "in_progress_count": self.in_progress_count,
            "high_priority_count": self.high_priority_count,
            "by_project": self.by_project,
            "by_category": self.by_category,
            "by_priority": self.by_priority,
            "by_status": self.by_status,
            "recent_items": self.recent_items,
            "filtered_items": self.filtered_items,
            "applied_filters": self.applied_filters,
        }


@dataclass
class DashboardRenderContext:
    """
    ダッシュボードレンダリングコンテキスト

    エグゼクティブダッシュボード全体のレンダリングに必要なデータを保持する。
    複数プロジェクトの健康状態、エスカレーション、レビュー待ち、バックログを集約。
    """
    # プロジェクト健康状態リスト
    projects: List[ProjectHealthData] = field(default_factory=list)

    # サマリデータ
    escalation_summary: EscalationSummary = field(default_factory=EscalationSummary)
    review_summary: PendingReviewSummary = field(default_factory=PendingReviewSummary)
    backlog_summary: BacklogSummary = field(default_factory=BacklogSummary)

    # 全体統計
    total_projects: int = 0
    healthy_projects: int = 0
    warning_projects: int = 0
    critical_projects: int = 0

    # メタデータ
    render_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    render_time: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    updated_by: str = "System (自動生成)"

    def calculate_totals(self) -> None:
        """
        プロジェクトリストから全体統計を計算
        """
        self.total_projects = len(self.projects)
        self.healthy_projects = sum(
            1 for p in self.projects if p.status == HealthStatus.HEALTHY
        )
        self.warning_projects = sum(
            1 for p in self.projects if p.status == HealthStatus.WARNING
        )
        self.critical_projects = sum(
            1 for p in self.projects if p.status == HealthStatus.CRITICAL
        )

    def to_dict(self) -> Dict[str, Any]:
        """テンプレート用辞書に変換"""
        # 全体統計を再計算
        self.calculate_totals()

        return {
            # プロジェクト一覧
            "projects": [
                {
                    "project_id": p.project_id,
                    "project_name": p.project_name,
                    "status": p.status.value,
                    "current_order_id": p.current_order_id,
                    "current_order_title": p.current_order_title,
                    "order_status": p.order_status,
                    "total_tasks": p.total_tasks,
                    "completed_tasks": p.completed_tasks,
                    "in_progress_tasks": p.in_progress_tasks,
                    "blocked_tasks": p.blocked_tasks,
                    "rework_tasks": p.rework_tasks,
                    "completion_rate": p.completion_rate,
                    "completion_rate_percent": int(p.completion_rate * 100),
                    "pending_reviews": p.pending_reviews,
                    "open_escalations": p.open_escalations,
                    "blocked_ratio": p.blocked_ratio,
                    "blocked_ratio_percent": int(p.blocked_ratio * 100),
                    "last_activity": p.last_activity,
                }
                for p in self.projects
            ],

            # サマリ
            "escalation_summary": self.escalation_summary.to_dict(),
            "review_summary": self.review_summary.to_dict(),
            "backlog_summary": self.backlog_summary.to_dict(),

            # 全体統計
            "total_projects": self.total_projects,
            "healthy_projects": self.healthy_projects,
            "warning_projects": self.warning_projects,
            "critical_projects": self.critical_projects,

            # メタデータ
            "render_date": self.render_date,
            "render_time": self.render_time,
            "updated_by": self.updated_by,
        }


def calculate_health(
    escalation_count: int,
    blocked_count: int,
    active_order_count: int,
    stagnant_task_exists: bool = False,
) -> HealthStatus:
    """
    プロジェクトの健康状態を計算する独立関数

    判定基準（TASK_312定義）:
    - 🔴 CRITICAL（問題）: escalation > 0 or 長期停滞（7日以上IN_PROGRESS変化なし）
    - 🟡 WARNING（警告）: active_orders >= 3 or blocked > 0
    - 🟢 HEALTHY（正常）: escalation = 0, blocked = 0, active_orders < 3

    Args:
        escalation_count: 未解決エスカレーション数
        blocked_count: BLOCKEDタスク数
        active_order_count: アクティブORDER数（IN_PROGRESS状態のORDER）
        stagnant_task_exists: 長期停滞タスクが存在するか（7日以上IN_PROGRESS変化なし）

    Returns:
        HealthStatus: 健康状態（CRITICAL / WARNING / HEALTHY）
    """
    # 🔴 CRITICAL条件
    # - エスカレーションが1件以上
    # - 長期停滞タスクが存在
    if escalation_count > 0:
        return HealthStatus.CRITICAL
    if stagnant_task_exists:
        return HealthStatus.CRITICAL

    # 🟡 WARNING条件
    # - アクティブORDERが3件以上
    # - BLOCKEDタスクが1件以上
    if active_order_count >= 3:
        return HealthStatus.WARNING
    if blocked_count > 0:
        return HealthStatus.WARNING

    # 🟢 HEALTHY条件
    # - 上記いずれにも該当しない
    return HealthStatus.HEALTHY


def detect_stagnant_tasks(
    tasks: List[Dict[str, Any]],
    stagnation_days: int = 7,
    reference_date: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    長期停滞タスクを検出

    Args:
        tasks: タスク情報のリスト（各タスクにはstatus, updated_atが必要）
        stagnation_days: 停滞と判定する日数（デフォルト7日）
        reference_date: 基準日（Noneの場合は現在日時）

    Returns:
        List[Dict]: 停滞タスクのリスト
    """
    if reference_date is None:
        reference_date = datetime.now()

    stagnant_tasks = []

    for task in tasks:
        if task.get("status") != "IN_PROGRESS":
            continue

        updated_at_str = task.get("updated_at")
        if not updated_at_str:
            continue

        # 日付文字列をパース
        try:
            if isinstance(updated_at_str, str):
                # ISO 8601形式またはSQLite形式に対応
                if "T" in updated_at_str:
                    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                else:
                    updated_at = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S")
            else:
                updated_at = updated_at_str
        except (ValueError, TypeError):
            continue

        # タイムゾーン情報を削除して比較
        if hasattr(updated_at, 'tzinfo') and updated_at.tzinfo is not None:
            updated_at = updated_at.replace(tzinfo=None)

        days_stagnant = (reference_date - updated_at).days

        if days_stagnant >= stagnation_days:
            stagnant_tasks.append({
                **task,
                "days_stagnant": days_stagnant,
            })

    return stagnant_tasks


def load_dashboard_context(
    db_path: Optional[Path] = None,
    include_inactive_projects: bool = False,
    backlog_priority_filter: Optional[List[str]] = None,
    backlog_status_filter: Optional[List[str]] = None,
    backlog_project_filter: Optional[str] = None,
) -> DashboardRenderContext:
    """
    DBからダッシュボードコンテキストを読み込む

    全プロジェクトの健康状態、エスカレーション、レビュー待ち、バックログを集約し、
    DashboardRenderContext を生成する。

    Args:
        db_path: データベースパス（Noneの場合はデフォルト）
        include_inactive_projects: 非アクティブプロジェクトを含めるか
        backlog_priority_filter: バックログ優先度フィルタ（例: ["High", "Medium"]）
        backlog_status_filter: バックログステータスフィルタ（例: ["TODO"]）
        backlog_project_filter: バックログプロジェクトフィルタ（例: "ai_pm_manager"）

    Returns:
        DashboardRenderContext: レンダリングコンテキスト

    Performance:
        目標: 3秒以内で完了
    """
    from utils.db import (
        get_connection,
        fetch_all,
        fetch_one,
        rows_to_dicts,
    )

    conn = get_connection(db_path)
    try:
        context = DashboardRenderContext()

        # ============================================================
        # 1. プロジェクト一覧 + ORDER/タスク統計
        # ============================================================
        projects_query = """
        SELECT
            p.id as project_id,
            p.name as project_name,
            p.status as project_status,
            p.current_order_id,
            p.updated_at as project_updated_at
        FROM projects p
        WHERE 1=1
        """
        if not include_inactive_projects:
            # is_activeカラムが存在するか確認
            try:
                result = fetch_all(conn, "PRAGMA table_info(projects)")
                column_names = [row["name"] for row in result]
                if "is_active" in column_names:
                    projects_query += " AND p.is_active = 1"
            except Exception:
                pass

        projects_query += " ORDER BY p.updated_at DESC"
        project_rows = fetch_all(conn, projects_query)

        for proj_row in project_rows:
            project_id = proj_row["project_id"]

            # ORDER統計を取得
            order_stats = fetch_one(
                conn,
                """
                SELECT
                    COUNT(*) as total_orders,
                    SUM(CASE WHEN status IN ('PLANNING', 'IN_PROGRESS', 'REVIEW') THEN 1 ELSE 0 END) as active_orders
                FROM orders
                WHERE project_id = ?
                """,
                (project_id,)
            )

            # タスク統計を取得
            task_stats = fetch_one(
                conn,
                """
                SELECT
                    COUNT(*) as total_tasks,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_tasks,
                    SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress_tasks,
                    SUM(CASE WHEN status = 'BLOCKED' THEN 1 ELSE 0 END) as blocked_tasks,
                    SUM(CASE WHEN status = 'REWORK' THEN 1 ELSE 0 END) as rework_tasks
                FROM tasks
                WHERE project_id = ?
                """,
                (project_id,)
            )

            # 現在のORDER情報を取得
            current_order = None
            if proj_row["current_order_id"]:
                current_order = fetch_one(
                    conn,
                    """
                    SELECT id, title, status
                    FROM orders
                    WHERE id = ? AND project_id = ?
                    """,
                    (proj_row["current_order_id"], project_id)
                )

            # エスカレーション数を取得
            escalation_count = fetch_one(
                conn,
                """
                SELECT COUNT(*) as count
                FROM escalations
                WHERE project_id = ? AND status = 'OPEN'
                """,
                (project_id,)
            )

            # レビュー待ち数を取得
            pending_review_count = fetch_one(
                conn,
                """
                SELECT COUNT(*) as count
                FROM tasks
                WHERE project_id = ? AND status = 'DONE' AND reviewed_at IS NULL
                """,
                (project_id,)
            )

            # IN_PROGRESSタスクの停滞チェック用
            in_progress_tasks = fetch_all(
                conn,
                """
                SELECT id, title, status, updated_at
                FROM tasks
                WHERE project_id = ? AND status = 'IN_PROGRESS'
                """,
                (project_id,)
            )
            stagnant_tasks = detect_stagnant_tasks(rows_to_dicts(in_progress_tasks))

            # ProjectHealthData を構築
            total_tasks = task_stats["total_tasks"] or 0
            completed_tasks = task_stats["completed_tasks"] or 0
            blocked_tasks = task_stats["blocked_tasks"] or 0

            completion_rate = completed_tasks / total_tasks if total_tasks > 0 else 0.0
            blocked_ratio = blocked_tasks / total_tasks if total_tasks > 0 else 0.0

            project_health = ProjectHealthData(
                project_id=project_id,
                project_name=proj_row["project_name"],
                current_order_id=proj_row["current_order_id"],
                current_order_title=current_order["title"] if current_order else None,
                order_status=current_order["status"] if current_order else None,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks,
                in_progress_tasks=task_stats["in_progress_tasks"] or 0,
                blocked_tasks=blocked_tasks,
                rework_tasks=task_stats["rework_tasks"] or 0,
                completion_rate=completion_rate,
                pending_reviews=pending_review_count["count"] if pending_review_count else 0,
                open_escalations=escalation_count["count"] if escalation_count else 0,
                blocked_ratio=blocked_ratio,
                last_activity=proj_row["project_updated_at"],
            )

            # 健康状態を計算
            project_health.status = calculate_health(
                escalation_count=project_health.open_escalations,
                blocked_count=project_health.blocked_tasks,
                active_order_count=order_stats["active_orders"] or 0,
                stagnant_task_exists=len(stagnant_tasks) > 0,
            )

            context.projects.append(project_health)

        # ============================================================
        # 2. 全エスカレーション（OPEN）
        # ============================================================
        open_escalations = fetch_all(
            conn,
            """
            SELECT
                e.id,
                e.task_id,
                e.project_id,
                e.title,
                e.status,
                e.created_at,
                e.resolved_at,
                julianday('now') - julianday(e.created_at) as days_open
            FROM escalations e
            WHERE e.status = 'OPEN'
            ORDER BY e.created_at ASC
            """
        )

        today = datetime.now().strftime("%Y-%m-%d")
        resolved_today = fetch_one(
            conn,
            """
            SELECT COUNT(*) as count
            FROM escalations
            WHERE status = 'RESOLVED' AND date(resolved_at) = ?
            """,
            (today,)
        )

        escalation_by_project: Dict[str, int] = {}
        for esc in open_escalations:
            proj_id = esc["project_id"]
            if proj_id:
                escalation_by_project[proj_id] = escalation_by_project.get(proj_id, 0) + 1

        context.escalation_summary = EscalationSummary(
            total_open=len(open_escalations),
            total_resolved_today=resolved_today["count"] if resolved_today else 0,
            oldest_open_days=int(open_escalations[0]["days_open"]) if open_escalations else 0,
            by_project=escalation_by_project,
            recent_escalations=[dict(row) for row in open_escalations[:5]],
        )

        # ============================================================
        # 3. 全承認待ち（PENDING / IN_REVIEW）
        # ============================================================
        pending_reviews = fetch_all(
            conn,
            """
            SELECT
                t.id as task_id,
                t.project_id,
                t.status,
                t.priority,
                t.updated_at as submitted_at,
                NULL as reviewer,
                t.title as task_title,
                julianday('now') - julianday(t.updated_at) as hours_pending
            FROM tasks t
            WHERE t.status = 'DONE' AND t.reviewed_at IS NULL
            ORDER BY
                CASE t.priority
                    WHEN 'P0' THEN 0
                    WHEN 'P1' THEN 1
                    WHEN 'P2' THEN 2
                END,
                t.updated_at ASC
            """
        )

        review_by_project: Dict[str, int] = {}
        total_pending = 0
        total_in_review = 0
        p0_count = 0
        p1_count = 0
        p2_count = 0

        for review in pending_reviews:
            proj_id = review["project_id"]
            if proj_id:
                review_by_project[proj_id] = review_by_project.get(proj_id, 0) + 1

            # reviewed_atがNULLのDONEタスクは全てレビュー待ち（PENDING相当）
            total_pending += 1

            if review["priority"] == "P0":
                p0_count += 1
            elif review["priority"] == "P1":
                p1_count += 1
            elif review["priority"] == "P2":
                p2_count += 1

        oldest_pending_hours = 0.0
        if pending_reviews:
            # hours_pending は日数で取得されるので24を掛ける
            oldest_pending_hours = (pending_reviews[0]["hours_pending"] or 0) * 24

        context.review_summary = PendingReviewSummary(
            total_pending=total_pending,
            total_in_review=total_in_review,
            p0_count=p0_count,
            p1_count=p1_count,
            p2_count=p2_count,
            by_project=review_by_project,
            oldest_pending_hours=oldest_pending_hours,
            pending_items=[dict(row) for row in pending_reviews[:10]],
        )

        # ============================================================
        # 4. バックログサマリ
        # ============================================================
        backlog_stats = fetch_one(
            conn,
            """
            SELECT
                COUNT(*) as total_items,
                SUM(CASE WHEN status = 'TODO' THEN 1 ELSE 0 END) as todo_count,
                SUM(CASE WHEN status = 'IN_PROGRESS' THEN 1 ELSE 0 END) as in_progress_count,
                SUM(CASE WHEN priority = 'High' THEN 1 ELSE 0 END) as high_priority_count
            FROM backlog_items
            """
        )

        backlog_by_project = fetch_all(
            conn,
            """
            SELECT project_id, COUNT(*) as count
            FROM backlog_items
            WHERE status IN ('TODO', 'IN_PROGRESS')
            GROUP BY project_id
            """
        )

        # 優先度別内訳を取得
        backlog_by_priority = fetch_all(
            conn,
            """
            SELECT priority, COUNT(*) as count
            FROM backlog_items
            WHERE status IN ('TODO', 'IN_PROGRESS')
            GROUP BY priority
            """
        )

        # ステータス別内訳を取得
        backlog_by_status = fetch_all(
            conn,
            """
            SELECT status, COUNT(*) as count
            FROM backlog_items
            GROUP BY status
            """
        )

        # categoryカラムが存在するかチェック（後方互換性）
        try:
            result = fetch_all(conn, "PRAGMA table_info(backlog_items)")
            backlog_columns = [row["name"] for row in result]
            has_category = "category" in backlog_columns
        except Exception:
            has_category = False

        if has_category:
            backlog_by_category = fetch_all(
                conn,
                """
                SELECT category, COUNT(*) as count
                FROM backlog_items
                WHERE status IN ('TODO', 'IN_PROGRESS') AND category IS NOT NULL
                GROUP BY category
                """
            )
        else:
            backlog_by_category = []

        # アクティブなバックログを取得（TODO, IN_PROGRESS, EXTERNALのみ）
        # 優先度順 → 作成日順でソート
        recent_backlog = fetch_all(
            conn,
            """
            SELECT
                id,
                project_id,
                title,
                priority,
                status,
                created_at
            FROM backlog_items
            WHERE status IN ('TODO', 'IN_PROGRESS', 'EXTERNAL')
            ORDER BY
                CASE priority
                    WHEN 'High' THEN 0
                    WHEN 'Medium' THEN 1
                    WHEN 'Low' THEN 2
                END,
                created_at DESC
            LIMIT 50
            """
        )

        # フィルタ結果を取得（フィルタが指定されている場合のみ）
        filtered_items = []
        applied_filters = {}
        if backlog_priority_filter or backlog_status_filter or backlog_project_filter:
            # フィルタ情報を記録
            applied_filters = {
                "priority": backlog_priority_filter,
                "status": backlog_status_filter,
                "project": backlog_project_filter,
            }

            # フィルタクエリを構築
            filter_query = """
            SELECT
                id,
                project_id,
                title,
                priority,
                status,
                created_at
            FROM backlog_items
            WHERE 1=1
            """
            filter_params: List[Any] = []

            if backlog_project_filter:
                filter_query += " AND project_id = ?"
                filter_params.append(backlog_project_filter)

            if backlog_status_filter:
                placeholders = ",".join(["?" for _ in backlog_status_filter])
                filter_query += f" AND status IN ({placeholders})"
                filter_params.extend(backlog_status_filter)

            if backlog_priority_filter:
                placeholders = ",".join(["?" for _ in backlog_priority_filter])
                filter_query += f" AND priority IN ({placeholders})"
                filter_params.extend(backlog_priority_filter)

            # ソート（優先度 → ステータス → 作成日）
            filter_query += """
            ORDER BY
                CASE priority
                    WHEN 'High' THEN 0
                    WHEN 'Medium' THEN 1
                    WHEN 'Low' THEN 2
                END,
                CASE status
                    WHEN 'TODO' THEN 0
                    WHEN 'IN_PROGRESS' THEN 1
                    WHEN 'DONE' THEN 2
                    WHEN 'CANCELED' THEN 3
                    WHEN 'EXTERNAL' THEN 4
                END,
                created_at DESC
            LIMIT 20
            """

            filtered_rows = fetch_all(conn, filter_query, tuple(filter_params))
            filtered_items = [dict(row) for row in filtered_rows]

        context.backlog_summary = BacklogSummary(
            total_items=backlog_stats["total_items"] or 0,
            todo_count=backlog_stats["todo_count"] or 0,
            in_progress_count=backlog_stats["in_progress_count"] or 0,
            high_priority_count=backlog_stats["high_priority_count"] or 0,
            by_project={row["project_id"]: row["count"] for row in backlog_by_project},
            by_category={row["category"]: row["count"] for row in backlog_by_category if row["category"]},
            by_priority={row["priority"]: row["count"] for row in backlog_by_priority if row["priority"]},
            by_status={row["status"]: row["count"] for row in backlog_by_status if row["status"]},
            recent_items=[dict(row) for row in recent_backlog],
            filtered_items=filtered_items,
            applied_filters=applied_filters,
        )

        # ============================================================
        # 5. 全体統計を計算
        # ============================================================
        context.calculate_totals()

        return context

    finally:
        conn.close()


def get_jinja_env(template_dir: Optional[Path] = None) -> Environment:
    """Jinja2環境を取得"""
    if template_dir is None:
        template_dir = TEMPLATE_DIR

    return Environment(
        loader=FileSystemLoader(str(template_dir)),
        autoescape=select_autoescape(default=False),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_dashboard(context: DashboardRenderContext, template_dir: Optional[Path] = None) -> str:
    """
    DASHBOARD.mdをレンダリング

    Args:
        context: レンダリングコンテキスト
        template_dir: テンプレートディレクトリ（Noneの場合はデフォルト）

    Returns:
        str: レンダリングされたMarkdown文字列
    """
    env = get_jinja_env(template_dir)
    template = env.get_template("dashboard.md.j2")
    return template.render(**context.to_dict())


def render_dashboard_to_file(
    context: DashboardRenderContext,
    output_path: Path,
    template_dir: Optional[Path] = None,
) -> Path:
    """
    DASHBOARD.mdをファイルに出力

    Args:
        context: レンダリングコンテキスト
        output_path: 出力ファイルパス
        template_dir: テンプレートディレクトリ

    Returns:
        Path: 出力ファイルパス
    """
    content = render_dashboard(context, template_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return output_path


def main():
    """CLI エントリポイント"""
    import json
    import time

    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="DBからDASHBOARD.mdを生成",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # ダッシュボードコンテキストをJSON出力
  python backend/render/dashboard.py --json

  # ファイルに出力（テンプレートが必要）
  python backend/render/dashboard.py -o DASHBOARD.md

  # 非アクティブプロジェクトも含める
  python backend/render/dashboard.py --all --json

  # バックログをフィルタして表示
  python backend/render/dashboard.py -o DASHBOARD.md --backlog-priority High Medium --backlog-status TODO

  # 特定プロジェクトのバックログをフィルタ
  python backend/render/dashboard.py -o DASHBOARD.md --backlog-project ai_pm_manager --backlog-status TODO
        """
    )

    parser.add_argument("--output", "-o", help="出力ファイルパス")
    parser.add_argument("--db", help="データベースファイルパス")
    parser.add_argument("--template-dir", help="テンプレートディレクトリパス")
    parser.add_argument("--json", action="store_true", help="JSON形式でコンテキストを出力")
    parser.add_argument("--all", dest="include_all", action="store_true",
                        help="非アクティブプロジェクトも含める")
    parser.add_argument("--perf", action="store_true", help="パフォーマンス測定を表示")
    # バックログフィルタオプション
    parser.add_argument("--backlog-priority", nargs="+",
                        choices=["High", "Medium", "Low"],
                        help="バックログを優先度でフィルタ（複数指定可）")
    parser.add_argument("--backlog-status", nargs="+",
                        choices=["TODO", "IN_PROGRESS", "DONE", "CANCELED", "EXTERNAL"],
                        help="バックログをステータスでフィルタ（複数指定可）")
    parser.add_argument("--backlog-project", help="バックログをプロジェクトでフィルタ")

    args = parser.parse_args()

    try:
        # パフォーマンス測定開始
        start_time = time.time()

        # DBからコンテキストを読み込み
        db_path = Path(args.db) if args.db else None
        context = load_dashboard_context(
            db_path=db_path,
            include_inactive_projects=args.include_all,
            backlog_priority_filter=args.backlog_priority,
            backlog_status_filter=args.backlog_status,
            backlog_project_filter=args.backlog_project,
        )

        elapsed = time.time() - start_time

        if args.perf:
            print(f"[PERF] load_dashboard_context: {elapsed:.3f}s", file=sys.stderr)

        if args.json:
            # JSON形式で出力
            output = context.to_dict()
            print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
        elif args.output:
            # テンプレートを使ってファイル出力
            template_dir = Path(args.template_dir) if args.template_dir else None
            output_path = Path(args.output)

            # テンプレート存在チェック
            template_path = (template_dir or TEMPLATE_DIR) / "dashboard.md.j2"
            if not template_path.exists():
                print(f"[WARNING] テンプレートが見つかりません: {template_path}", file=sys.stderr)
                print("テンプレートはTASK_313で作成予定です。", file=sys.stderr)
                print("代わりに --json オプションでJSON出力を確認してください。", file=sys.stderr)
                sys.exit(1)

            render_dashboard_to_file(context, output_path, template_dir)
            print(f"DASHBOARD.md を出力しました: {output_path}")
        else:
            # サマリ表示
            print("ダッシュボードサマリ")
            print("=" * 50)
            print(f"\n【プロジェクト】")
            print(f"  合計: {context.total_projects}件")
            print(f"  🟢 HEALTHY: {context.healthy_projects}件")
            print(f"  🟡 WARNING: {context.warning_projects}件")
            print(f"  🔴 CRITICAL: {context.critical_projects}件")

            print(f"\n【エスカレーション】")
            print(f"  未解決: {context.escalation_summary.total_open}件")
            print(f"  本日解決: {context.escalation_summary.total_resolved_today}件")
            if context.escalation_summary.oldest_open_days > 0:
                print(f"  最長未解決: {context.escalation_summary.oldest_open_days}日")

            print(f"\n【承認待ち】")
            print(f"  PENDING: {context.review_summary.total_pending}件")
            print(f"  IN_REVIEW: {context.review_summary.total_in_review}件")
            print(f"  P0（最優先）: {context.review_summary.p0_count}件")

            print(f"\n【バックログ】")
            print(f"  合計: {context.backlog_summary.total_items}件")
            print(f"  TODO: {context.backlog_summary.todo_count}件")
            print(f"  High優先: {context.backlog_summary.high_priority_count}件")

            if args.perf:
                print(f"\n[PERF] 処理時間: {elapsed:.3f}秒")

    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
