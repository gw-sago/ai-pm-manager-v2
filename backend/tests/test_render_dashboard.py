"""
AI PM Framework - ダッシュボードレンダリングテスト

render/dashboard.py の単体テスト
特にcalculate_health()関数とdetect_stagnant_tasks()関数のテスト
"""

import unittest
from datetime import datetime, timedelta
from pathlib import Path

# テスト対象モジュールのインポート
import sys
# aipm-db ディレクトリをパスに追加（パッケージとしてではなく直接インポート）
_aipm_db_path = str(Path(__file__).resolve().parent.parent)
if _aipm_db_path not in sys.path:
    sys.path.insert(0, _aipm_db_path)

# __init__.py を経由しないように直接インポート
from render.dashboard import (
    HealthStatus,
    calculate_health,
    detect_stagnant_tasks,
    ProjectHealthData,
    DashboardRenderContext,
    EscalationSummary,
    PendingReviewSummary,
    BacklogSummary,
)


class TestCalculateHealth(unittest.TestCase):
    """calculate_health() 関数のテスト"""

    def test_healthy_all_zero(self):
        """正常: escalation=0, blocked=0, active_orders=0"""
        result = calculate_health(
            escalation_count=0,
            blocked_count=0,
            active_order_count=0,
        )
        self.assertEqual(result, HealthStatus.HEALTHY)

    def test_healthy_low_active_orders(self):
        """正常: escalation=0, blocked=0, active_orders=2"""
        result = calculate_health(
            escalation_count=0,
            blocked_count=0,
            active_order_count=2,
        )
        self.assertEqual(result, HealthStatus.HEALTHY)

    def test_warning_high_active_orders(self):
        """警告: active_orders=3"""
        result = calculate_health(
            escalation_count=0,
            blocked_count=0,
            active_order_count=3,
        )
        self.assertEqual(result, HealthStatus.WARNING)

    def test_warning_high_active_orders_above_3(self):
        """警告: active_orders=5"""
        result = calculate_health(
            escalation_count=0,
            blocked_count=0,
            active_order_count=5,
        )
        self.assertEqual(result, HealthStatus.WARNING)

    def test_warning_blocked_exists(self):
        """警告: blocked>0"""
        result = calculate_health(
            escalation_count=0,
            blocked_count=1,
            active_order_count=0,
        )
        self.assertEqual(result, HealthStatus.WARNING)

    def test_warning_multiple_blocked(self):
        """警告: blocked=3"""
        result = calculate_health(
            escalation_count=0,
            blocked_count=3,
            active_order_count=1,
        )
        self.assertEqual(result, HealthStatus.WARNING)

    def test_critical_escalation_exists(self):
        """問題: escalation>0"""
        result = calculate_health(
            escalation_count=1,
            blocked_count=0,
            active_order_count=0,
        )
        self.assertEqual(result, HealthStatus.CRITICAL)

    def test_critical_multiple_escalations(self):
        """問題: escalation=3"""
        result = calculate_health(
            escalation_count=3,
            blocked_count=0,
            active_order_count=0,
        )
        self.assertEqual(result, HealthStatus.CRITICAL)

    def test_critical_stagnant_task(self):
        """問題: 長期停滞タスク存在"""
        result = calculate_health(
            escalation_count=0,
            blocked_count=0,
            active_order_count=0,
            stagnant_task_exists=True,
        )
        self.assertEqual(result, HealthStatus.CRITICAL)

    def test_critical_escalation_overrides_warning(self):
        """escalation>0はWARNING条件よりも優先（CRITICAL）"""
        # active_orders>=3の条件もあるが、escalationがあるのでCRITICAL
        result = calculate_health(
            escalation_count=1,
            blocked_count=2,
            active_order_count=5,
        )
        self.assertEqual(result, HealthStatus.CRITICAL)

    def test_critical_stagnant_overrides_warning(self):
        """長期停滞はWARNING条件よりも優先（CRITICAL）"""
        result = calculate_health(
            escalation_count=0,
            blocked_count=2,
            active_order_count=5,
            stagnant_task_exists=True,
        )
        self.assertEqual(result, HealthStatus.CRITICAL)

    def test_warning_blocked_and_active_orders(self):
        """警告: blocked>0 and active_orders>=3"""
        result = calculate_health(
            escalation_count=0,
            blocked_count=1,
            active_order_count=3,
        )
        self.assertEqual(result, HealthStatus.WARNING)


class TestDetectStagnantTasks(unittest.TestCase):
    """detect_stagnant_tasks() 関数のテスト"""

    def test_no_stagnant_tasks_empty_list(self):
        """空のリストでは停滞タスクなし"""
        result = detect_stagnant_tasks([])
        self.assertEqual(result, [])

    def test_no_stagnant_tasks_recent_update(self):
        """最近更新されたIN_PROGRESSタスクは停滞なし"""
        now = datetime.now()
        tasks = [
            {
                "id": "TASK_001",
                "status": "IN_PROGRESS",
                "updated_at": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
        result = detect_stagnant_tasks(tasks, stagnation_days=7, reference_date=now)
        self.assertEqual(result, [])

    def test_stagnant_task_detected(self):
        """7日以上更新されていないIN_PROGRESSタスクを検出"""
        now = datetime.now()
        tasks = [
            {
                "id": "TASK_001",
                "status": "IN_PROGRESS",
                "updated_at": (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
        result = detect_stagnant_tasks(tasks, stagnation_days=7, reference_date=now)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], "TASK_001")
        self.assertEqual(result[0]["days_stagnant"], 10)

    def test_stagnant_task_exactly_7_days(self):
        """ちょうど7日経過したタスクも検出される"""
        now = datetime.now()
        tasks = [
            {
                "id": "TASK_001",
                "status": "IN_PROGRESS",
                "updated_at": (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
        result = detect_stagnant_tasks(tasks, stagnation_days=7, reference_date=now)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["days_stagnant"], 7)

    def test_stagnant_task_6_days_not_detected(self):
        """6日経過したタスクは検出されない"""
        now = datetime.now()
        tasks = [
            {
                "id": "TASK_001",
                "status": "IN_PROGRESS",
                "updated_at": (now - timedelta(days=6)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
        result = detect_stagnant_tasks(tasks, stagnation_days=7, reference_date=now)
        self.assertEqual(result, [])

    def test_non_in_progress_not_detected(self):
        """IN_PROGRESS以外のタスクは検出されない"""
        now = datetime.now()
        tasks = [
            {
                "id": "TASK_001",
                "status": "COMPLETED",
                "updated_at": (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "id": "TASK_002",
                "status": "BLOCKED",
                "updated_at": (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "id": "TASK_003",
                "status": "QUEUED",
                "updated_at": (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
            },
        ]
        result = detect_stagnant_tasks(tasks, stagnation_days=7, reference_date=now)
        self.assertEqual(result, [])

    def test_mixed_tasks(self):
        """混合リストから停滞タスクのみを検出"""
        now = datetime.now()
        tasks = [
            {
                "id": "TASK_001",
                "status": "IN_PROGRESS",
                "updated_at": (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "id": "TASK_002",
                "status": "IN_PROGRESS",
                "updated_at": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "id": "TASK_003",
                "status": "COMPLETED",
                "updated_at": (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S"),
            },
            {
                "id": "TASK_004",
                "status": "IN_PROGRESS",
                "updated_at": (now - timedelta(days=15)).strftime("%Y-%m-%d %H:%M:%S"),
            },
        ]
        result = detect_stagnant_tasks(tasks, stagnation_days=7, reference_date=now)
        self.assertEqual(len(result), 2)
        ids = [t["id"] for t in result]
        self.assertIn("TASK_001", ids)
        self.assertIn("TASK_004", ids)

    def test_iso_format_date(self):
        """ISO 8601形式の日付もパース可能"""
        now = datetime.now()
        tasks = [
            {
                "id": "TASK_001",
                "status": "IN_PROGRESS",
                "updated_at": (now - timedelta(days=10)).isoformat(),
            }
        ]
        result = detect_stagnant_tasks(tasks, stagnation_days=7, reference_date=now)
        self.assertEqual(len(result), 1)

    def test_custom_stagnation_days(self):
        """カスタム停滞日数での判定"""
        now = datetime.now()
        tasks = [
            {
                "id": "TASK_001",
                "status": "IN_PROGRESS",
                "updated_at": (now - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        ]
        # 3日以上で停滞とみなす
        result = detect_stagnant_tasks(tasks, stagnation_days=3, reference_date=now)
        self.assertEqual(len(result), 1)


class TestProjectHealthDataCalculateStatus(unittest.TestCase):
    """ProjectHealthData.calculate_status() メソッドのテスト（TASK_310実装分）"""

    def test_unknown_when_no_tasks(self):
        """タスクがない場合はUNKNOWN"""
        data = ProjectHealthData(
            project_id="TEST_PJ",
            project_name="Test Project",
            total_tasks=0,
        )
        result = data.calculate_status()
        self.assertEqual(result, HealthStatus.UNKNOWN)

    def test_critical_with_escalation(self):
        """エスカレーションがある場合はCRITICAL"""
        data = ProjectHealthData(
            project_id="TEST_PJ",
            project_name="Test Project",
            total_tasks=10,
            open_escalations=1,
        )
        result = data.calculate_status()
        self.assertEqual(result, HealthStatus.CRITICAL)

    def test_critical_with_high_blocked_ratio(self):
        """ブロック率50%以上でCRITICAL"""
        data = ProjectHealthData(
            project_id="TEST_PJ",
            project_name="Test Project",
            total_tasks=10,
            blocked_ratio=0.5,
        )
        result = data.calculate_status()
        self.assertEqual(result, HealthStatus.CRITICAL)

    def test_warning_with_blocked_ratio(self):
        """ブロック率20%以上でWARNING"""
        data = ProjectHealthData(
            project_id="TEST_PJ",
            project_name="Test Project",
            total_tasks=10,
            blocked_ratio=0.2,
        )
        result = data.calculate_status()
        self.assertEqual(result, HealthStatus.WARNING)

    def test_warning_with_rework(self):
        """差戻しタスクがあればWARNING"""
        data = ProjectHealthData(
            project_id="TEST_PJ",
            project_name="Test Project",
            total_tasks=10,
            rework_tasks=1,
        )
        result = data.calculate_status()
        self.assertEqual(result, HealthStatus.WARNING)

    def test_warning_with_many_pending_reviews(self):
        """レビュー待ち5件以上でWARNING"""
        data = ProjectHealthData(
            project_id="TEST_PJ",
            project_name="Test Project",
            total_tasks=10,
            pending_reviews=5,
        )
        result = data.calculate_status()
        self.assertEqual(result, HealthStatus.WARNING)

    def test_healthy_normal_state(self):
        """正常な状態ではHEALTHY"""
        data = ProjectHealthData(
            project_id="TEST_PJ",
            project_name="Test Project",
            total_tasks=10,
            completed_tasks=5,
            in_progress_tasks=3,
            blocked_ratio=0.1,
        )
        result = data.calculate_status()
        self.assertEqual(result, HealthStatus.HEALTHY)


class TestDashboardRenderContext(unittest.TestCase):
    """DashboardRenderContext のテスト"""

    def test_calculate_totals(self):
        """全体統計の計算"""
        projects = [
            ProjectHealthData(
                project_id="PJ1",
                project_name="Project 1",
                status=HealthStatus.HEALTHY,
            ),
            ProjectHealthData(
                project_id="PJ2",
                project_name="Project 2",
                status=HealthStatus.WARNING,
            ),
            ProjectHealthData(
                project_id="PJ3",
                project_name="Project 3",
                status=HealthStatus.CRITICAL,
            ),
            ProjectHealthData(
                project_id="PJ4",
                project_name="Project 4",
                status=HealthStatus.HEALTHY,
            ),
        ]

        context = DashboardRenderContext(projects=projects)
        context.calculate_totals()

        self.assertEqual(context.total_projects, 4)
        self.assertEqual(context.healthy_projects, 2)
        self.assertEqual(context.warning_projects, 1)
        self.assertEqual(context.critical_projects, 1)

    def test_to_dict(self):
        """to_dict()メソッドのテスト"""
        projects = [
            ProjectHealthData(
                project_id="PJ1",
                project_name="Project 1",
                status=HealthStatus.HEALTHY,
                total_tasks=10,
                completed_tasks=8,
                completion_rate=0.8,
            ),
        ]

        context = DashboardRenderContext(projects=projects)
        result = context.to_dict()

        self.assertEqual(result["total_projects"], 1)
        self.assertEqual(result["healthy_projects"], 1)
        self.assertEqual(len(result["projects"]), 1)
        self.assertEqual(result["projects"][0]["project_id"], "PJ1")
        self.assertEqual(result["projects"][0]["completion_rate_percent"], 80)


if __name__ == "__main__":
    unittest.main()
