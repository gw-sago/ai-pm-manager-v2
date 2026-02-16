#!/usr/bin/env python3
"""
SpecValidator のユニットテスト

テスト対象: backend/pm/spec_validator.py

テスト項目:
- detect_ambiguous_expressions() が曖昧表現を検出する
- detect_ambiguous_expressions() がクリーンな説明で空を返す
- validate_acceptance_criteria() が必須フィールド欠落を検出する
- validate_acceptance_criteria() が不正なACタイプを検出する
- validate_dependencies() が循環依存を検出する
- validate_dependencies() が存在しない依存先を検出する
- validate_target_files() が欠落ファイルを報告する
- validate_spec() が統合結果とスコアを返す
"""

import sys
import tempfile
from pathlib import Path

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
sys.path.insert(0, str(_package_root))

import unittest

from pm.spec_validator import (
    SpecValidator,
    SpecValidatorError,
    ValidationResult,
    AC_TYPES,
    AMBIGUOUS_EXPRESSIONS,
)


class TestDetectAmbiguousExpressions(unittest.TestCase):
    """detect_ambiguous_expressions() のテスト"""

    def setUp(self):
        self.validator = SpecValidator()

    def test_detects_tekisetsuni(self):
        """'適切に' を検出すること"""
        tasks = [
            {
                "title": "エラー処理を適切に実装する",
                "description": "例外処理を追加する",
            },
        ]
        warnings = self.validator.detect_ambiguous_expressions(tasks)
        self.assertTrue(len(warnings) > 0)
        expressions_found = [w["expression"] for w in warnings]
        self.assertIn("適切に", expressions_found)

    def test_detects_hitsuyou_ni_oujite(self):
        """'必要に応じて' を検出すること"""
        tasks = [
            {
                "title": "ログ出力追加",
                "description": "必要に応じてデバッグログを追加する",
            },
        ]
        warnings = self.validator.detect_ambiguous_expressions(tasks)
        self.assertTrue(len(warnings) > 0)
        expressions_found = [w["expression"] for w in warnings]
        self.assertIn("必要に応じて", expressions_found)

    def test_detects_multiple_ambiguous_expressions(self):
        """複数の曖昧表現を同時に検出すること"""
        tasks = [
            {
                "title": "適切にエラー処理を実装",
                "description": "必要に応じてログを追加し、できるだけ効率よく処理する",
            },
        ]
        warnings = self.validator.detect_ambiguous_expressions(tasks)
        expressions_found = [w["expression"] for w in warnings]
        self.assertIn("適切に", expressions_found)
        self.assertIn("必要に応じて", expressions_found)
        self.assertIn("できるだけ", expressions_found)

    def test_returns_empty_for_clean_description(self):
        """曖昧表現のないタスクで空リストを返すこと"""
        tasks = [
            {
                "title": "spec_generator.pyを作成する",
                "description": "SpecGeneratorクラスを実装し、enhance_prompt()メソッドを定義する",
            },
        ]
        warnings = self.validator.detect_ambiguous_expressions(tasks)
        self.assertEqual(len(warnings), 0)

    def test_reports_correct_field(self):
        """検出箇所のfield（title/description）が正しいこと"""
        tasks = [
            {
                "title": "適切にモジュール作成",
                "description": "具体的な説明文",
            },
        ]
        warnings = self.validator.detect_ambiguous_expressions(tasks)
        self.assertTrue(len(warnings) > 0)
        self.assertEqual(warnings[0]["field"], "title")

    def test_description_field_detection(self):
        """description内の曖昧表現でfield='description'になること"""
        tasks = [
            {
                "title": "モジュール作成",
                "description": "適宜テストを追加する",
            },
        ]
        warnings = self.validator.detect_ambiguous_expressions(tasks)
        desc_warnings = [w for w in warnings if w["field"] == "description"]
        self.assertTrue(len(desc_warnings) > 0)

    def test_warning_contains_context(self):
        """警告にcontextが含まれること"""
        tasks = [
            {
                "title": "モジュール作成",
                "description": "設定値をよしなに調整して最適化する",
            },
        ]
        warnings = self.validator.detect_ambiguous_expressions(tasks)
        self.assertTrue(len(warnings) > 0)
        self.assertIn("context", warnings[0])
        self.assertTrue(len(warnings[0]["context"]) > 0)


class TestValidateAcceptanceCriteria(unittest.TestCase):
    """validate_acceptance_criteria() のテスト"""

    def setUp(self):
        self.validator = SpecValidator()

    def test_rejects_missing_required_fields(self):
        """必須フィールド欠落のACエントリを検出すること"""
        tasks = [
            {
                "title": "テストタスク",
                "acceptance_criteria": [
                    {"criterion": "ファイルが存在する", "target": "file.py"},
                    # type 欠落
                ],
            },
        ]
        results = self.validator.validate_acceptance_criteria(tasks)
        errors = [r for r in results if r["severity"] == "error"]
        self.assertTrue(len(errors) > 0)
        error_checks = [e["check"] for e in errors]
        self.assertTrue(
            any("ac_field_type" in c for c in error_checks),
            f"Expected ac_field_type error, got: {error_checks}",
        )

    def test_rejects_missing_criterion_field(self):
        """criterion欠落のACエントリを検出すること"""
        tasks = [
            {
                "title": "テストタスク",
                "acceptance_criteria": [
                    {"type": "file_exists", "target": "file.py"},
                    # criterion 欠落
                ],
            },
        ]
        results = self.validator.validate_acceptance_criteria(tasks)
        errors = [r for r in results if r["severity"] == "error"]
        self.assertTrue(len(errors) > 0)

    def test_rejects_invalid_ac_type(self):
        """不正なACタイプを検出すること"""
        tasks = [
            {
                "title": "テストタスク",
                "acceptance_criteria": [
                    {
                        "criterion": "実行可能であること",
                        "type": "invalid_type",
                        "target": "module.py",
                    },
                ],
            },
        ]
        results = self.validator.validate_acceptance_criteria(tasks)
        errors = [r for r in results if r["severity"] == "error"]
        self.assertTrue(len(errors) > 0)
        error_checks = [e["check"] for e in errors]
        self.assertIn("ac_type_valid", error_checks)

    def test_reports_missing_ac(self):
        """AC未定義タスクをエラーとして報告すること"""
        tasks = [
            {
                "title": "ACなしタスク",
                "description": "ACが定義されていない",
            },
        ]
        results = self.validator.validate_acceptance_criteria(tasks)
        errors = [r for r in results if r["severity"] == "error"]
        self.assertTrue(len(errors) > 0)
        error_checks = [e["check"] for e in errors]
        self.assertIn("ac_exists", error_checks)

    def test_valid_ac_passes(self):
        """有効なACエントリが通過すること"""
        tasks = [
            {
                "title": "有効なタスク",
                "acceptance_criteria": [
                    {
                        "criterion": "ファイルが存在する",
                        "type": "file_exists",
                        "target": "backend/pm/new_module.py",
                    },
                ],
            },
        ]
        results = self.validator.validate_acceptance_criteria(tasks)
        errors = [r for r in results if r["severity"] == "error"]
        self.assertEqual(len(errors), 0)

    def test_all_valid_ac_types_accepted(self):
        """全ての有効なACタイプが受け入れられること"""
        for ac_type in AC_TYPES:
            tasks = [
                {
                    "title": f"{ac_type}テスト",
                    "acceptance_criteria": [
                        {
                            "criterion": f"{ac_type}の検証",
                            "type": ac_type,
                            "target": "test/target.py",
                        },
                    ],
                },
            ]
            results = self.validator.validate_acceptance_criteria(tasks)
            type_errors = [
                r for r in results
                if r["severity"] == "error" and r["check"] == "ac_type_valid"
            ]
            self.assertEqual(
                len(type_errors), 0,
                f"AC type '{ac_type}' should be valid but got errors",
            )

    def test_non_list_ac_rejected(self):
        """acceptance_criteriaがリストでない場合にエラーとなること"""
        tasks = [
            {
                "title": "不正ACタスク",
                "acceptance_criteria": "これはリストではない",
            },
        ]
        results = self.validator.validate_acceptance_criteria(tasks)
        errors = [r for r in results if r["severity"] == "error"]
        self.assertTrue(len(errors) > 0)


class TestValidateDependencies(unittest.TestCase):
    """validate_dependencies() のテスト"""

    def setUp(self):
        self.validator = SpecValidator()

    def test_detects_circular_dependency(self):
        """循環依存を検出すること"""
        tasks = [
            {
                "title": "タスクA",
                "depends_on": ["タスクB"],
            },
            {
                "title": "タスクB",
                "depends_on": ["タスクA"],
            },
        ]
        errors = self.validator.validate_dependencies(tasks)
        self.assertTrue(len(errors) > 0)
        circular_errors = [e for e in errors if e["check"] == "circular_dependency"]
        self.assertTrue(len(circular_errors) > 0)

    def test_detects_missing_dependency_reference(self):
        """存在しない依存先を検出すること"""
        tasks = [
            {
                "title": "タスクA",
                "depends_on": ["存在しないタスク"],
            },
        ]
        errors = self.validator.validate_dependencies(tasks)
        self.assertTrue(len(errors) > 0)
        missing_errors = [e for e in errors if e["check"] == "dependency_exists"]
        self.assertTrue(len(missing_errors) > 0)
        self.assertIn("存在しないタスク", missing_errors[0]["message"])

    def test_valid_dependencies_pass(self):
        """有効な依存関係でエラーがないこと"""
        tasks = [
            {
                "title": "タスクA",
                "depends_on": [],
            },
            {
                "title": "タスクB",
                "depends_on": ["タスクA"],
            },
        ]
        errors = self.validator.validate_dependencies(tasks)
        self.assertEqual(len(errors), 0)

    def test_no_dependencies_pass(self):
        """依存関係なしでエラーがないこと"""
        tasks = [
            {"title": "独立タスク1"},
            {"title": "独立タスク2"},
        ]
        errors = self.validator.validate_dependencies(tasks)
        self.assertEqual(len(errors), 0)

    def test_three_node_cycle_detected(self):
        """3ノードの循環依存を検出すること"""
        tasks = [
            {"title": "A", "depends_on": ["B"]},
            {"title": "B", "depends_on": ["C"]},
            {"title": "C", "depends_on": ["A"]},
        ]
        errors = self.validator.validate_dependencies(tasks)
        circular_errors = [e for e in errors if e["check"] == "circular_dependency"]
        self.assertTrue(len(circular_errors) > 0)


class TestValidateTargetFiles(unittest.TestCase):
    """validate_target_files() のテスト"""

    def setUp(self):
        self.validator = SpecValidator()

    def test_reports_missing_files_with_project_root(self):
        """project_root指定時に存在しないファイルを報告すること"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tasks = [
                {
                    "title": "テストタスク",
                    "target_files": ["nonexistent/deeply/nested/file.py"],
                },
            ]
            results = self.validator.validate_target_files(tasks, project_root=tmpdir)
            # 親ディレクトリも存在しないのでwarning
            warnings = [r for r in results if r["severity"] == "warning"]
            self.assertTrue(len(warnings) > 0)

    def test_reports_new_file_when_parent_exists(self):
        """親ディレクトリが存在する場合に新規ファイルと推定すること"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 親ディレクトリを作成
            parent = Path(tmpdir) / "existing_dir"
            parent.mkdir()

            tasks = [
                {
                    "title": "新規ファイル作成タスク",
                    "target_files": ["existing_dir/new_file.py"],
                },
            ]
            results = self.validator.validate_target_files(tasks, project_root=tmpdir)
            info_results = [r for r in results if r.get("severity") == "info"]
            self.assertTrue(len(info_results) > 0)

    def test_no_check_without_project_root(self):
        """project_root未指定時にファイル存在チェックをスキップすること"""
        tasks = [
            {
                "title": "テストタスク",
                "target_files": ["any/path/file.py"],
            },
        ]
        results = self.validator.validate_target_files(tasks)
        # パス形式の問題がなければ結果は空
        file_missing = [
            r for r in results
            if r["check"] in ("file_new", "file_missing_dir")
        ]
        self.assertEqual(len(file_missing), 0)

    def test_non_list_target_files_error(self):
        """target_filesがリストでない場合にエラーとなること"""
        tasks = [
            {
                "title": "不正タスク",
                "target_files": "not_a_list.py",
            },
        ]
        results = self.validator.validate_target_files(tasks)
        errors = [r for r in results if r["severity"] == "error"]
        self.assertTrue(len(errors) > 0)

    def test_empty_path_in_target_files_error(self):
        """target_filesに空パスがある場合にエラーとなること"""
        tasks = [
            {
                "title": "空パスタスク",
                "target_files": ["valid/path.py", ""],
            },
        ]
        results = self.validator.validate_target_files(tasks)
        errors = [r for r in results if r["severity"] == "error"]
        self.assertTrue(len(errors) > 0)


class TestValidateSpec(unittest.TestCase):
    """validate_spec() の統合テスト"""

    def setUp(self):
        self.validator = SpecValidator()

    def test_returns_combined_results_with_score(self):
        """統合結果にis_valid, errors, warnings, scoreが含まれること"""
        tasks = [
            {
                "title": "有効なタスク",
                "description": "具体的な実装を行う",
                "acceptance_criteria": [
                    {
                        "criterion": "ファイルが存在する",
                        "type": "file_exists",
                        "target": "scripts/module.py",
                    },
                ],
                "depends_on": [],
                "target_files": ["scripts/module.py"],
            },
        ]
        result = self.validator.validate_spec(tasks)
        self.assertIsInstance(result, ValidationResult)
        self.assertIsInstance(result.is_valid, bool)
        self.assertIsInstance(result.errors, list)
        self.assertIsInstance(result.warnings, list)
        self.assertIsInstance(result.score, float)
        self.assertGreaterEqual(result.score, 0.0)
        self.assertLessEqual(result.score, 1.0)

    def test_valid_spec_returns_high_score(self):
        """有効なSpecで高スコアが返ること"""
        tasks = [
            {
                "title": "モジュール作成",
                "description": "SpecGeneratorクラスを実装する",
                "acceptance_criteria": [
                    {
                        "criterion": "spec_generator.pyが存在する",
                        "type": "file_exists",
                        "target": "pm/spec_generator.py",
                    },
                ],
                "depends_on": [],
                "target_files": ["pm/spec_generator.py"],
            },
        ]
        result = self.validator.validate_spec(tasks)
        self.assertTrue(result.is_valid)
        self.assertGreater(result.score, 0.5)

    def test_invalid_spec_returns_low_score(self):
        """エラーのあるSpecで低スコアが返ること"""
        tasks = [
            {
                "title": "適切にモジュール作成",
                "description": "必要に応じてテストを追加する",
                "acceptance_criteria": [
                    {
                        "criterion": "ファイルが存在する",
                        "type": "invalid_type",
                        "target": "file.py",
                    },
                ],
                "depends_on": ["存在しないタスク"],
                "target_files": [],
            },
        ]
        result = self.validator.validate_spec(tasks)
        self.assertFalse(result.is_valid)
        self.assertLess(result.score, 1.0)

    def test_empty_tasks_returns_invalid(self):
        """空タスクリストでis_valid=Falseが返ること"""
        result = self.validator.validate_spec([])
        self.assertFalse(result.is_valid)
        self.assertEqual(result.score, 0.0)
        self.assertTrue(len(result.errors) > 0)

    def test_to_dict(self):
        """ValidationResult.to_dict()が正しい形式を返すこと"""
        tasks = [
            {
                "title": "テストタスク",
                "description": "テスト説明",
                "acceptance_criteria": [
                    {
                        "criterion": "テスト通過",
                        "type": "test_passes",
                        "target": "test_example.py",
                    },
                ],
            },
        ]
        result = self.validator.validate_spec(tasks)
        d = result.to_dict()
        self.assertIn("is_valid", d)
        self.assertIn("errors", d)
        self.assertIn("warnings", d)
        self.assertIn("score", d)
        self.assertIn("error_count", d)
        self.assertIn("warning_count", d)
        self.assertEqual(d["error_count"], len(d["errors"]))
        self.assertEqual(d["warning_count"], len(d["warnings"]))

    def test_ambiguous_expression_included_in_warnings(self):
        """曖昧表現がwarningsに含まれること"""
        tasks = [
            {
                "title": "よしなにモジュール作成",
                "description": "SpecGeneratorクラスを実装する",
                "acceptance_criteria": [
                    {
                        "criterion": "ファイルが存在する",
                        "type": "file_exists",
                        "target": "module.py",
                    },
                ],
            },
        ]
        result = self.validator.validate_spec(tasks)
        self.assertTrue(len(result.warnings) > 0)
        # 曖昧表現の警告が含まれるか
        ambiguous_warnings = [
            w for w in result.warnings if w.get("check") == "ambiguous_expression"
        ]
        self.assertTrue(len(ambiguous_warnings) > 0)


class TestCustomAmbiguousExpressions(unittest.TestCase):
    """カスタム曖昧表現リストのテスト"""

    def test_custom_expressions_override_defaults(self):
        """カスタム曖昧表現がデフォルトを上書きすること（BUG_001対策確認）"""
        custom = ("カスタム表現",)
        validator = SpecValidator(ambiguous_expressions=custom)
        self.assertEqual(validator.ambiguous_expressions, custom)

    def test_default_expressions_immutable(self):
        """デフォルトの曖昧表現リストがイミュータブル（tuple）であること"""
        self.assertIsInstance(AMBIGUOUS_EXPRESSIONS, tuple)


class TestValidationResult(unittest.TestCase):
    """ValidationResult データクラスのテスト"""

    def test_default_values(self):
        """デフォルト値が正しいこと"""
        result = ValidationResult()
        self.assertTrue(result.is_valid)
        self.assertEqual(result.errors, [])
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.score, 1.0)

    def test_mutable_default_not_shared(self):
        """複数インスタンス間でリストが共有されないこと（BUG_001対策確認）"""
        result1 = ValidationResult()
        result2 = ValidationResult()
        result1.errors.append({"check": "test", "message": "error"})
        self.assertEqual(len(result2.errors), 0)


if __name__ == "__main__":
    unittest.main()
