#!/usr/bin/env python3
"""
SpecGenerator のユニットテスト

テスト対象: backend/pm/spec_generator.py

テスト項目:
- enhance_prompt() がacceptance_criteriaを含むプロンプトを返す
- generate_acceptance_criteria() がtarget_files付きタスクで有効なACを返す
- generate_acceptance_criteria() がtarget_files無しタスクでフォールバックACを返す
- merge_acceptance_criteria() が重複除去マージを行う
- format_acceptance_criteria_markdown() がチェックボックス付きMarkdownを返す
- 空入力時のエラーハンドリング
"""

import sys
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
sys.path.insert(0, str(_package_root))

import unittest

from pm.spec_generator import SpecGenerator, SpecGeneratorError, AC_TYPES


class TestEnhancePrompt(unittest.TestCase):
    """enhance_prompt() のテスト"""

    def setUp(self):
        self.gen = SpecGenerator()

    def test_returns_string_containing_acceptance_criteria(self):
        """プロンプトに 'acceptance_criteria' が含まれること"""
        order_content = "## 概要\nテスト用のORDER内容です。"
        result = self.gen.enhance_prompt(order_content)
        self.assertIsInstance(result, str)
        self.assertIn("acceptance_criteria", result)

    def test_returns_string_containing_order_content(self):
        """プロンプトにORDER内容が含まれること"""
        order_content = "## 概要\nサンプルORDER: 新しいモジュールを作成する。"
        result = self.gen.enhance_prompt(order_content)
        self.assertIn("サンプルORDER", result)

    def test_prompt_contains_ac_types(self):
        """プロンプトにACタイプの説明が含まれること"""
        order_content = "テスト用ORDER内容"
        result = self.gen.enhance_prompt(order_content)
        for ac_type in AC_TYPES:
            self.assertIn(ac_type, result)

    def test_prompt_contains_json_format_instruction(self):
        """プロンプトにJSON形式の指示が含まれること"""
        order_content = "テスト用ORDER内容"
        result = self.gen.enhance_prompt(order_content)
        self.assertIn("JSON", result)

    def test_empty_order_content_raises_error(self):
        """空のORDER内容でSpecGeneratorErrorが発生すること"""
        with self.assertRaises(SpecGeneratorError):
            self.gen.enhance_prompt("")

    def test_whitespace_only_order_content_raises_error(self):
        """空白のみのORDER内容でSpecGeneratorErrorが発生すること"""
        with self.assertRaises(SpecGeneratorError):
            self.gen.enhance_prompt("   \n\t  ")


class TestGenerateAcceptanceCriteria(unittest.TestCase):
    """generate_acceptance_criteria() のテスト"""

    def setUp(self):
        self.gen = SpecGenerator()

    def test_generates_file_exists_ac_for_target_files(self):
        """target_files付きタスクでfile_exists ACが生成されること"""
        task_def = {
            "title": "モジュール作成",
            "description": "新しいPythonモジュールを作成する",
            "target_files": ["backend/pm/new_module.py"],
        }
        criteria = self.gen.generate_acceptance_criteria(task_def)
        self.assertTrue(len(criteria) > 0)

        file_exists_acs = [ac for ac in criteria if ac["type"] == "file_exists"]
        self.assertTrue(len(file_exists_acs) > 0)
        self.assertEqual(
            file_exists_acs[0]["target"],
            "backend/pm/new_module.py",
        )

    def test_generates_import_works_ac_for_py_files(self):
        """Pythonファイルのtarget_filesでimport_works ACが生成されること"""
        task_def = {
            "title": "ユーティリティ作成",
            "description": "ヘルパー関数を実装する",
            "target_files": ["backend/utils/helper.py"],
        }
        criteria = self.gen.generate_acceptance_criteria(task_def)
        import_acs = [ac for ac in criteria if ac["type"] == "import_works"]
        self.assertTrue(len(import_acs) > 0)

    def test_fallback_ac_for_task_without_target_files(self):
        """target_files無しタスクでフォールバックACが生成されること"""
        task_def = {
            "title": "ドキュメント更新",
            "description": "READMEの内容を更新する",
            "target_files": [],
        }
        criteria = self.gen.generate_acceptance_criteria(task_def)
        self.assertTrue(len(criteria) > 0)
        # フォールバックはoutput_containsタイプ
        self.assertEqual(criteria[0]["type"], "output_contains")
        self.assertIn("ドキュメント更新", criteria[0]["target"])

    def test_fallback_ac_for_task_with_none_target_files(self):
        """target_filesがNoneのタスクでもフォールバックACが生成されること"""
        task_def = {
            "title": "設定確認",
            "description": "設定値の確認を行う",
        }
        criteria = self.gen.generate_acceptance_criteria(task_def)
        self.assertTrue(len(criteria) > 0)

    def test_all_ac_entries_have_required_fields(self):
        """全ACエントリにcriterion, type, targetフィールドがあること"""
        task_def = {
            "title": "テスト作成",
            "description": "テストファイルtest_exampleを作成する",
            "target_files": [
                "backend/tests/test_example.py",
                "backend/pm/example.py",
            ],
        }
        criteria = self.gen.generate_acceptance_criteria(task_def)
        for ac in criteria:
            self.assertIn("criterion", ac, f"criterion missing in {ac}")
            self.assertIn("type", ac, f"type missing in {ac}")
            self.assertIn("target", ac, f"target missing in {ac}")
            self.assertIn(ac["type"], AC_TYPES, f"Invalid type: {ac['type']}")

    def test_deduplicates_by_target(self):
        """同じtarget+typeの重複が除去されること"""
        task_def = {
            "title": "モジュール作成",
            "description": "新しいファイルを作成する",
            "target_files": ["backend/pm/module.py"],
        }
        criteria = self.gen.generate_acceptance_criteria(task_def)

        # (type, target)ペアのユニーク性を確認
        seen = set()
        for ac in criteria:
            key = (ac["type"], ac["target"])
            self.assertNotIn(key, seen, f"Duplicate AC: {key}")
            seen.add(key)

    def test_test_keyword_generates_test_passes_ac(self):
        """テスト関連キーワードを含むタスクでtest_passes ACが生成されること"""
        task_def = {
            "title": "ユニットテスト作成",
            "description": "test_validationのテストケースを追加する",
            "target_files": ["backend/tests/test_validation.py"],
        }
        criteria = self.gen.generate_acceptance_criteria(task_def)
        test_acs = [ac for ac in criteria if ac["type"] == "test_passes"]
        self.assertTrue(len(test_acs) > 0)


class TestMergeAcceptanceCriteria(unittest.TestCase):
    """merge_acceptance_criteria() のテスト"""

    def setUp(self):
        self.gen = SpecGenerator()

    def test_merge_ai_and_generated(self):
        """AI生成ACと推論生成ACが正しくマージされること"""
        ai_criteria = [
            {
                "criterion": "ファイルが存在する",
                "type": "file_exists",
                "target": "path/to/file.py",
            },
        ]
        generated_criteria = [
            {
                "criterion": "モジュールがインポート可能",
                "type": "import_works",
                "target": "module.name",
            },
        ]
        merged = self.gen.merge_acceptance_criteria(ai_criteria, generated_criteria)
        self.assertEqual(len(merged), 2)
        # AI生成が先
        self.assertEqual(merged[0]["type"], "file_exists")
        self.assertEqual(merged[1]["type"], "import_works")

    def test_deduplicates_on_merge(self):
        """マージ時に同じ(type, target)が重複除去されること"""
        ai_criteria = [
            {
                "criterion": "ファイルが存在する",
                "type": "file_exists",
                "target": "path/to/file.py",
            },
        ]
        generated_criteria = [
            {
                "criterion": "ファイル path/to/file.py が存在する",
                "type": "file_exists",
                "target": "path/to/file.py",
            },
        ]
        merged = self.gen.merge_acceptance_criteria(ai_criteria, generated_criteria)
        self.assertEqual(len(merged), 1)
        # AI側のcriterionが優先される
        self.assertEqual(merged[0]["criterion"], "ファイルが存在する")

    def test_none_ai_criteria(self):
        """ai_criteriaがNoneでもエラーにならないこと"""
        generated_criteria = [
            {
                "criterion": "テスト通過",
                "type": "test_passes",
                "target": "test_file.py",
            },
        ]
        merged = self.gen.merge_acceptance_criteria(None, generated_criteria)
        self.assertEqual(len(merged), 1)

    def test_invalid_ai_criteria_skipped(self):
        """不正なAIのACエントリがスキップされること"""
        ai_criteria = [
            {"criterion": "有効なエントリ", "type": "file_exists", "target": "a.py"},
            {"criterion": "typeなしエントリ", "target": "b.py"},  # type欠落
            {"type": "file_exists", "target": "c.py"},  # criterion欠落 - 空でないので有効ではない
        ]
        generated_criteria = []
        merged = self.gen.merge_acceptance_criteria(ai_criteria, generated_criteria)
        # typeなし・criterion空のエントリはスキップされる
        # "criterion"キーが存在しないエントリはスキップ
        valid_count = sum(
            1 for ac in ai_criteria
            if all(k in ac and ac[k] for k in ("criterion", "type", "target"))
            and ac.get("type") in AC_TYPES
        )
        self.assertEqual(len(merged), valid_count)


class TestFormatAcceptanceCriteriaMarkdown(unittest.TestCase):
    """format_acceptance_criteria_markdown() のテスト"""

    def setUp(self):
        self.gen = SpecGenerator()

    def test_produces_markdown_with_checkboxes(self):
        """チェックボックス付きMarkdownが生成されること"""
        criteria = [
            {
                "criterion": "ファイルが存在する",
                "type": "file_exists",
                "target": "path/to/file.py",
            },
            {
                "criterion": "テストが通過する",
                "type": "test_passes",
                "target": "test_example.py",
            },
        ]
        result = self.gen.format_acceptance_criteria_markdown(criteria)
        self.assertIn("- [ ]", result)
        self.assertIn("AC-1", result)
        self.assertIn("AC-2", result)
        self.assertIn("ファイル存在", result)  # type_label
        self.assertIn("テスト通過", result)  # type_label
        self.assertIn("`path/to/file.py`", result)
        self.assertIn("`test_example.py`", result)

    def test_empty_criteria_returns_fallback(self):
        """空リストでフォールバックメッセージが返ること"""
        result = self.gen.format_acceptance_criteria_markdown([])
        self.assertIn("Acceptance Criteria なし", result)

    def test_contains_verification_target(self):
        """検証対象の表示が含まれること"""
        criteria = [
            {
                "criterion": "モジュールがインポート可能",
                "type": "import_works",
                "target": "pm.spec_generator",
            },
        ]
        result = self.gen.format_acceptance_criteria_markdown(criteria)
        self.assertIn("検証対象", result)
        self.assertIn("`pm.spec_generator`", result)


class TestCustomAcTypeHints(unittest.TestCase):
    """カスタムac_type_hintsのテスト"""

    def test_custom_hints_override_defaults(self):
        """カスタムヒントがデフォルトを上書きすること（BUG_001対策確認）"""
        custom_hints = {
            "file_exists": ["custom_keyword"],
        }
        gen = SpecGenerator(ac_type_hints=custom_hints)
        self.assertEqual(gen.ac_type_hints, custom_hints)

    def test_default_hints_not_shared_between_instances(self):
        """複数インスタンス間でデフォルトヒントが共有されないこと（BUG_001対策確認）"""
        gen1 = SpecGenerator()
        gen2 = SpecGenerator()
        gen1.ac_type_hints["file_exists"].append("extra_keyword")
        # gen2のヒントには影響しないこと
        self.assertNotIn("extra_keyword", gen2.ac_type_hints["file_exists"])


if __name__ == "__main__":
    unittest.main()
