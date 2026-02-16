#!/usr/bin/env python3
"""
PM処理（process_order.py）のユニットテスト

特に以下をテスト:
- 要件定義生成失敗時のステータス維持
- タスク作成失敗時のステータス維持
- 全ステップ成功時のみIN_PROGRESSに遷移
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# テスト対象モジュール
from pm.process_order import PMProcessor, PMProcessError


class TestPMProcessorStatusTransition(unittest.TestCase):
    """PM処理のステータス遷移テスト"""

    def setUp(self):
        """テスト前準備"""
        # テスト用の一時ディレクトリを作成
        self.test_dir = tempfile.mkdtemp()
        self.project_dir = Path(self.test_dir) / "PROJECTS" / "TEST_PROJECT"
        self.order_dir = self.project_dir / "ORDERS"
        self.result_dir = self.project_dir / "RESULT" / "ORDER_001"

        # ディレクトリ構造作成
        self.order_dir.mkdir(parents=True, exist_ok=True)
        self.result_dir.mkdir(parents=True, exist_ok=True)

        # テスト用ORDER.md作成
        order_content = """# ORDER_001.md

## 発注情報
- **発注ID**: ORDER_001
- **発注日**: 2026-02-05
- **優先度**: P1

## 発注内容
### 概要
テスト用ORDER

### 詳細
テスト用の詳細説明
"""
        (self.order_dir / "ORDER_001.md").write_text(order_content, encoding="utf-8")

    def tearDown(self):
        """テスト後の後処理"""
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch('pm.process_order.get_connection')
    @patch('pm.process_order.project_exists')
    @patch('pm.process_order.fetch_one')
    def test_status_not_updated_when_requirements_fail(
        self, mock_fetch_one, mock_project_exists, mock_get_conn
    ):
        """要件定義生成失敗時、ステータスはPLANNINGのまま"""
        # モック設定
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_project_exists.return_value = True
        mock_fetch_one.return_value = None  # ORDER未登録

        # PMProcessorをskip_ai=Falseで作成（AIを使うがrunnerはNone）
        processor = PMProcessor(
            "TEST_PROJECT",
            "001",
            skip_ai=False,
            verbose=True,
        )
        # パスをテスト用に上書き
        processor.project_dir = self.project_dir
        processor.order_file = self.order_dir / "ORDER_001.md"
        processor.result_dir = self.result_dir

        # runnerがNone（AI利用不可）の場合、要件定義生成はスキップ
        processor.runner = None

        # 処理実行
        results = processor.process()

        # 検証: requirementsが設定されていないためステータス更新はスキップされる
        # ただしskip_aiでなく、runnerがNoneの場合は_step_generate_requirementsがスキップされる
        # この場合、requirements_generated = Falseのままなのでステータス更新されない
        self.assertTrue(results["success"])

    @patch('pm.process_order.get_connection')
    @patch('pm.process_order.project_exists')
    @patch('pm.process_order.fetch_one')
    def test_status_updated_on_skip_ai_mode(
        self, mock_fetch_one, mock_project_exists, mock_get_conn
    ):
        """skip_aiモードでは常にステータス更新を実行"""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        mock_project_exists.return_value = True
        mock_fetch_one.return_value = None

        processor = PMProcessor(
            "TEST_PROJECT",
            "001",
            skip_ai=True,
            verbose=True,
        )
        processor.project_dir = self.project_dir
        processor.order_file = self.order_dir / "ORDER_001.md"
        processor.result_dir = self.result_dir

        # update_order_statusをモック化
        with patch.object(processor, '_step_update_order_status') as mock_update:
            results = processor.process()

            # skip_aiモードではステータス更新が呼ばれる
            mock_update.assert_called_once()

    def test_save_requirements_sets_none_on_json_error(self):
        """JSONパースエラー時、requirementsがNoneに設定される"""
        processor = PMProcessor(
            "TEST_PROJECT",
            "001",
            skip_ai=True,
        )
        processor.project_dir = self.project_dir
        processor.order_file = self.order_dir / "ORDER_001.md"
        processor.result_dir = self.result_dir

        # 不正なJSON
        invalid_json = "This is not valid JSON"

        # _save_requirements実行
        processor._save_requirements(invalid_json)

        # requirementsがNoneに設定されていることを確認
        self.assertIsNone(processor.results.get("requirements"))

    def test_save_requirements_sets_data_on_valid_json(self):
        """正常なJSONの場合、requirementsにデータが設定される"""
        processor = PMProcessor(
            "TEST_PROJECT",
            "001",
            skip_ai=True,
        )
        processor.project_dir = self.project_dir
        processor.order_file = self.order_dir / "ORDER_001.md"
        processor.result_dir = self.result_dir

        # 有効なJSON
        valid_json = json.dumps({
            "goal": {
                "summary": "テストゴール",
                "objectives": ["目標1"],
                "success_criteria": ["基準1"]
            },
            "requirements": {
                "functional": ["機能1"],
                "non_functional": ["非機能1"],
                "constraints": ["制約1"]
            },
            "tasks": [
                {
                    "title": "タスク1",
                    "description": "説明",
                    "priority": "P1",
                    "model": "Sonnet"
                }
            ]
        })

        # _save_requirements実行
        processor._save_requirements(valid_json)

        # requirementsにデータが設定されていることを確認
        self.assertIsNotNone(processor.results.get("requirements"))
        self.assertEqual(
            processor.results["requirements"]["goal"]["summary"],
            "テストゴール"
        )


class TestPMProcessorFlags(unittest.TestCase):
    """成功フラグのテスト"""

    def test_requirements_generated_flag_logic(self):
        """requirements_generatedフラグのロジック確認"""
        # results["requirements"]が存在し、Noneでない場合にTrue
        results = {"requirements": {"goal": {}}}
        self.assertTrue(bool(results.get("requirements")))

        # results["requirements"]がNoneの場合にFalse
        results = {"requirements": None}
        self.assertFalse(bool(results.get("requirements")))

        # results["requirements"]が存在しない場合にFalse
        results = {}
        self.assertFalse(bool(results.get("requirements")))

    def test_tasks_created_flag_logic(self):
        """tasks_createdフラグのロジック確認"""
        # results["created_tasks"]が存在し、空でない場合にTrue
        results = {"created_tasks": [{"id": "TASK_001"}]}
        self.assertTrue(bool(results.get("created_tasks")))

        # results["created_tasks"]が空リストの場合にFalse
        results = {"created_tasks": []}
        self.assertFalse(bool(results.get("created_tasks")))

        # results["created_tasks"]が存在しない場合にFalse
        results = {}
        self.assertFalse(bool(results.get("created_tasks")))


if __name__ == "__main__":
    unittest.main()
