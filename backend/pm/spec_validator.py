#!/usr/bin/env python3
"""
AI PM Framework - Spec Validator

SpecGenerator が生成したタスク仕様（Spec）の品質を検証するモジュール。
曖昧表現検出、AC検証可能性チェック、依存関係整合性チェック、
target_files存在確認を行い、総合的な品質スコアを算出する。

Usage (standalone):
    from pm.spec_validator import SpecValidator

    validator = SpecValidator()
    result = validator.validate_spec(tasks, project_root="/path/to/project")

Integration with process_order.py:
    PMProcessor._step_create_tasks() の前にバリデーションを挟むことで、
    品質の低い Spec が DB 登録されるのを防止する。
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# --- AC Type Definitions (spec_generator.py と同一) ---
AC_TYPES = (
    "file_exists",
    "function_defined",
    "test_passes",
    "import_works",
    "output_contains",
)

# --- 曖昧表現リスト ---
# タスク説明に含まれるべきでない曖昧な日本語表現
AMBIGUOUS_EXPRESSIONS = (
    "適切に",
    "必要に応じて",
    "など",
    "等",
    "適宜",
    "できるだけ",
    "可能であれば",
    "なるべく",
    "場合によっては",
    "よしなに",
    "いい感じに",
    "うまく",
    "ちゃんと",
    "しっかり",
    "きちんと",
)


class SpecValidatorError(Exception):
    """SpecValidator 処理エラー"""
    pass


class ValidationResult:
    """
    バリデーション結果を格納するデータクラス。

    Attributes:
        is_valid: 全体の合否（errorsが0件ならTrue）
        errors: ブロッキング問題のリスト
        warnings: 非ブロッキング問題のリスト
        score: 品質スコア 0.0-1.0
    """

    def __init__(
        self,
        *,
        is_valid: bool = True,
        errors: Optional[List[Dict[str, str]]] = None,
        warnings: Optional[List[Dict[str, str]]] = None,
        score: float = 1.0,
    ):
        # BUG_001対策: ミュータブルデフォルト引数を回避
        self.is_valid = is_valid
        self.errors = errors if errors is not None else []
        self.warnings = warnings if warnings is not None else []
        self.score = score

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "is_valid": self.is_valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "score": self.score,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
        }


class SpecValidator:
    """
    タスク仕様（Spec）の品質を検証するバリデータ。

    以下の4つの検証を実行し、総合スコアを算出する:
    1. 曖昧表現検出
    2. AC検証可能性チェック
    3. 依存関係整合性チェック
    4. target_files存在確認

    Attributes:
        ambiguous_expressions: 検出対象の曖昧表現リスト
    """

    def __init__(
        self,
        *,
        ambiguous_expressions: Optional[Tuple[str, ...]] = None,
    ):
        """
        Args:
            ambiguous_expressions: 検出対象の曖昧表現タプル。
                                   None の場合はデフォルト（AMBIGUOUS_EXPRESSIONS）を使用。
                                   (BUG_001対策: ミュータブルデフォルト引数を回避)
        """
        if ambiguous_expressions is not None:
            self.ambiguous_expressions = ambiguous_expressions
        else:
            self.ambiguous_expressions = AMBIGUOUS_EXPRESSIONS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_ambiguous_expressions(
        self, tasks: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """
        タスク説明から曖昧表現を検出する。

        Args:
            tasks: タスク定義のリスト。各タスクは以下のキーを参照:
                - title (str): タスク名
                - description (str): タスク説明

        Returns:
            警告のリスト。各要素は:
                {
                    "task_title": str,
                    "field": str,  ("title" or "description")
                    "expression": str,
                    "context": str,  (表現を含む前後テキスト)
                    "severity": "warning"
                }
        """
        warnings: List[Dict[str, str]] = []

        for task in tasks:
            title = task.get("title", "") or ""
            description = task.get("description", "") or ""

            # タイトルを検査
            for expr in self.ambiguous_expressions:
                if expr in title:
                    context = self._extract_context(title, expr)
                    warnings.append({
                        "task_title": title,
                        "field": "title",
                        "expression": expr,
                        "context": context,
                        "severity": "warning",
                    })

            # 説明を検査
            for expr in self.ambiguous_expressions:
                if expr in description:
                    context = self._extract_context(description, expr)
                    warnings.append({
                        "task_title": title,
                        "field": "description",
                        "expression": expr,
                        "context": context,
                        "severity": "warning",
                    })

        return warnings

    def validate_acceptance_criteria(
        self, tasks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        各タスクの Acceptance Criteria が検証可能かチェックする。

        チェック項目:
        - AC が存在するか
        - 各ACエントリに必須フィールド (criterion, type, target) があるか
        - type が有効値 (AC_TYPES) であるか
        - target が空でなく具体的であるか

        Args:
            tasks: タスク定義のリスト。各タスクは以下のキーを参照:
                - title (str): タスク名
                - acceptance_criteria (list): ACエントリのリスト

        Returns:
            検証結果のリスト。各要素は:
                {
                    "task_title": str,
                    "ac_index": int or None,
                    "check": str,
                    "passed": bool,
                    "message": str,
                    "severity": "error" or "warning"
                }
        """
        results: List[Dict[str, Any]] = []

        for task in tasks:
            title = task.get("title", "") or ""
            criteria = task.get("acceptance_criteria")

            # AC が存在しない場合
            if not criteria:
                results.append({
                    "task_title": title,
                    "ac_index": None,
                    "check": "ac_exists",
                    "passed": False,
                    "message": f"タスク「{title}」にacceptance_criteriaが未定義です",
                    "severity": "error",
                })
                continue

            if not isinstance(criteria, list):
                results.append({
                    "task_title": title,
                    "ac_index": None,
                    "check": "ac_type",
                    "passed": False,
                    "message": f"タスク「{title}」のacceptance_criteriaがリストではありません",
                    "severity": "error",
                })
                continue

            # 各ACエントリを検証
            for i, ac in enumerate(criteria):
                results.extend(self._validate_single_ac(title, i, ac))

        return results

    def validate_dependencies(
        self, tasks: List[Dict[str, Any]]
    ) -> List[Dict[str, str]]:
        """
        タスク間の依存関係の整合性をチェックする。

        チェック項目:
        - depends_on の参照先がタスクセット内に存在するか
        - 循環依存が存在しないか

        Args:
            tasks: タスク定義のリスト。各タスクは以下のキーを参照:
                - title (str): タスク名
                - depends_on (list): 依存タスク名のリスト

        Returns:
            エラーのリスト。各要素は:
                {
                    "task_title": str,
                    "check": str,
                    "message": str,
                    "severity": "error"
                }
        """
        errors: List[Dict[str, str]] = []

        # タスク名の集合を作成
        task_titles: Set[str] = set()
        for task in tasks:
            title = task.get("title", "") or ""
            if title:
                task_titles.add(title)

        # 依存関係グラフを構築
        dependency_graph: Dict[str, List[str]] = {}
        for task in tasks:
            title = task.get("title", "") or ""
            depends_on = task.get("depends_on") or []

            if not isinstance(depends_on, list):
                depends_on = [depends_on]

            dependency_graph[title] = []

            for dep in depends_on:
                dep_str = str(dep)
                if dep_str and dep_str not in task_titles:
                    errors.append({
                        "task_title": title,
                        "check": "dependency_exists",
                        "message": (
                            f"タスク「{title}」の依存先「{dep_str}」が"
                            f"タスクセット内に存在しません"
                        ),
                        "severity": "error",
                    })
                else:
                    dependency_graph[title].append(dep_str)

        # 循環依存の検出
        cycles = self._detect_cycles(dependency_graph)
        for cycle in cycles:
            cycle_str = " -> ".join(cycle)
            errors.append({
                "task_title": cycle[0],
                "check": "circular_dependency",
                "message": f"循環依存を検出: {cycle_str}",
                "severity": "error",
            })

        return errors

    def validate_target_files(
        self,
        tasks: List[Dict[str, Any]],
        project_root: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        target_files の存在確認を行う。

        - 既存ファイルを変更するタスク: ファイルが実在するかチェック
        - 新規ファイルを作成するタスク: ディレクトリ構造が妥当かチェック

        Args:
            tasks: タスク定義のリスト。各タスクは以下のキーを参照:
                - title (str): タスク名
                - target_files (list[str]): 対象ファイルパス一覧
            project_root: プロジェクトルートパス。Noneの場合はファイル存在チェックをスキップ。

        Returns:
            警告/エラーのリスト。各要素は:
                {
                    "task_title": str,
                    "file_path": str,
                    "check": str,
                    "message": str,
                    "severity": "warning" or "error"
                }
        """
        results: List[Dict[str, str]] = []

        for task in tasks:
            title = task.get("title", "") or ""
            target_files = task.get("target_files") or []

            if not isinstance(target_files, list):
                results.append({
                    "task_title": title,
                    "file_path": "",
                    "check": "target_files_type",
                    "message": (
                        f"タスク「{title}」のtarget_filesがリストではありません"
                    ),
                    "severity": "error",
                })
                continue

            for file_path in target_files:
                if not isinstance(file_path, str) or not file_path.strip():
                    results.append({
                        "task_title": title,
                        "file_path": str(file_path),
                        "check": "file_path_empty",
                        "message": (
                            f"タスク「{title}」のtarget_filesに空のパスがあります"
                        ),
                        "severity": "error",
                    })
                    continue

                # パスの妥当性チェック
                path_issues = self._validate_path_format(file_path)
                for issue in path_issues:
                    results.append({
                        "task_title": title,
                        "file_path": file_path,
                        "check": "path_format",
                        "message": issue,
                        "severity": "warning",
                    })

                # ファイル存在チェック（project_root指定時のみ）
                if project_root:
                    full_path = Path(project_root) / file_path
                    if not full_path.exists():
                        # 親ディレクトリの存在で新規か既存か判定
                        parent_dir = full_path.parent
                        if parent_dir.exists():
                            # 親ディレクトリは存在 -> 新規ファイル作成と推定
                            results.append({
                                "task_title": title,
                                "file_path": file_path,
                                "check": "file_new",
                                "message": (
                                    f"ファイル「{file_path}」は存在しません"
                                    f"（新規作成と推定）"
                                ),
                                "severity": "info",
                            })
                        else:
                            # 親ディレクトリも存在しない -> 警告
                            results.append({
                                "task_title": title,
                                "file_path": file_path,
                                "check": "file_missing_dir",
                                "message": (
                                    f"ファイル「{file_path}」のディレクトリ"
                                    f"「{parent_dir}」が存在しません"
                                ),
                                "severity": "warning",
                            })

        return results

    def validate_spec(
        self,
        tasks: List[Dict[str, Any]],
        *,
        project_root: Optional[str] = None,
    ) -> ValidationResult:
        """
        全検証を統合実行し、総合結果を返す。

        Args:
            tasks: タスク定義のリスト
            project_root: プロジェクトルートパス（target_files存在確認用）

        Returns:
            ValidationResult: 総合バリデーション結果
                - is_valid: errorsが0件ならTrue
                - errors: ブロッキング問題
                - warnings: 非ブロッキング問題
                - score: 品質スコア 0.0-1.0
        """
        all_errors: List[Dict[str, str]] = []
        all_warnings: List[Dict[str, str]] = []

        # タスクが空の場合
        if not tasks:
            return ValidationResult(
                is_valid=False,
                errors=[{
                    "check": "tasks_empty",
                    "message": "タスクが定義されていません",
                    "severity": "error",
                }],
                score=0.0,
            )

        # --- 1. 曖昧表現検出 ---
        ambiguous_warnings = self.detect_ambiguous_expressions(tasks)
        for w in ambiguous_warnings:
            all_warnings.append({
                "check": "ambiguous_expression",
                "task_title": w["task_title"],
                "message": (
                    f"タスク「{w['task_title']}」の{w['field']}に"
                    f"曖昧表現「{w['expression']}」があります: "
                    f"...{w['context']}..."
                ),
                "severity": "warning",
            })

        # --- 2. AC検証可能性チェック ---
        ac_results = self.validate_acceptance_criteria(tasks)
        for r in ac_results:
            if r["severity"] == "error":
                all_errors.append({
                    "check": r["check"],
                    "task_title": r.get("task_title", ""),
                    "message": r["message"],
                    "severity": "error",
                })
            elif r["severity"] == "warning":
                all_warnings.append({
                    "check": r["check"],
                    "task_title": r.get("task_title", ""),
                    "message": r["message"],
                    "severity": "warning",
                })
            # "info" severity items are pass results - skip them

        # --- 3. 依存関係整合性チェック ---
        dep_errors = self.validate_dependencies(tasks)
        for e in dep_errors:
            all_errors.append({
                "check": e["check"],
                "task_title": e.get("task_title", ""),
                "message": e["message"],
                "severity": "error",
            })

        # --- 4. target_files存在確認 ---
        file_results = self.validate_target_files(tasks, project_root)
        for r in file_results:
            if r["severity"] == "error":
                all_errors.append({
                    "check": r["check"],
                    "task_title": r.get("task_title", ""),
                    "message": r["message"],
                    "severity": "error",
                })
            elif r["severity"] == "warning":
                all_warnings.append({
                    "check": r["check"],
                    "task_title": r.get("task_title", ""),
                    "message": r["message"],
                    "severity": "warning",
                })
            # "info" は無視（ログのみ）

        # --- スコア算出 ---
        score = self._calculate_score(
            task_count=len(tasks),
            error_count=len(all_errors),
            warning_count=len(all_warnings),
            ambiguous_count=len(ambiguous_warnings),
            ac_results=ac_results,
        )

        is_valid = len(all_errors) == 0

        result = ValidationResult(
            is_valid=is_valid,
            errors=all_errors,
            warnings=all_warnings,
            score=score,
        )

        logger.info(
            f"Spec検証完了: valid={is_valid}, "
            f"errors={len(all_errors)}, warnings={len(all_warnings)}, "
            f"score={score:.2f}"
        )

        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_context(self, text: str, expression: str, window: int = 15) -> str:
        """
        テキスト中の表現の前後を抽出してコンテキストを返す。

        Args:
            text: 検索対象テキスト
            expression: 検出した表現
            window: 前後に含める文字数

        Returns:
            前後を含むコンテキスト文字列
        """
        idx = text.find(expression)
        if idx < 0:
            return expression

        start = max(0, idx - window)
        end = min(len(text), idx + len(expression) + window)
        return text[start:end]

    def _validate_single_ac(
        self, task_title: str, ac_index: int, ac: Any
    ) -> List[Dict[str, Any]]:
        """
        単一のACエントリを検証する。

        Args:
            task_title: タスク名
            ac_index: ACのインデックス（0始まり）
            ac: ACエントリ（辞書であることが期待される）

        Returns:
            検証結果のリスト
        """
        results: List[Dict[str, Any]] = []

        # 辞書型チェック
        if not isinstance(ac, dict):
            results.append({
                "task_title": task_title,
                "ac_index": ac_index,
                "check": "ac_dict",
                "passed": False,
                "message": (
                    f"タスク「{task_title}」のAC[{ac_index}]が辞書型ではありません"
                ),
                "severity": "error",
            })
            return results

        # 必須フィールド確認
        required_fields = ("criterion", "type", "target")
        for field in required_fields:
            if field not in ac or not ac[field]:
                results.append({
                    "task_title": task_title,
                    "ac_index": ac_index,
                    "check": f"ac_field_{field}",
                    "passed": False,
                    "message": (
                        f"タスク「{task_title}」のAC[{ac_index}]に"
                        f"必須フィールド「{field}」がありません"
                    ),
                    "severity": "error",
                })

        # type の有効値チェック
        ac_type = ac.get("type", "")
        if ac_type and ac_type not in AC_TYPES:
            results.append({
                "task_title": task_title,
                "ac_index": ac_index,
                "check": "ac_type_valid",
                "passed": False,
                "message": (
                    f"タスク「{task_title}」のAC[{ac_index}]のtype"
                    f"「{ac_type}」が不正です"
                    f"（有効値: {', '.join(AC_TYPES)}）"
                ),
                "severity": "error",
            })

        # target の具体性チェック
        target = ac.get("target", "")
        if target:
            target_issues = self._check_target_specificity(target, ac_type)
            for issue in target_issues:
                results.append({
                    "task_title": task_title,
                    "ac_index": ac_index,
                    "check": "ac_target_specificity",
                    "passed": False,
                    "message": (
                        f"タスク「{task_title}」のAC[{ac_index}]の"
                        f"target: {issue}"
                    ),
                    "severity": "warning",
                })

        # 全チェック通過
        has_errors = any(r["severity"] == "error" for r in results)
        if not has_errors:
            results.append({
                "task_title": task_title,
                "ac_index": ac_index,
                "check": "ac_valid",
                "passed": True,
                "message": (
                    f"タスク「{task_title}」のAC[{ac_index}]は有効です"
                ),
                "severity": "info",
            })

        return results

    def _check_target_specificity(self, target: str, ac_type: str) -> List[str]:
        """
        target の値が具体的か（曖昧でないか）を検証する。

        Args:
            target: ACのtarget値
            ac_type: ACのtype値

        Returns:
            問題があれば警告メッセージのリスト
        """
        issues: List[str] = []

        # 短すぎる target は曖昧の可能性
        if len(target.strip()) < 3:
            issues.append(
                f"target「{target}」が短すぎます（3文字未満）"
            )

        # file_exists, import_works はパス形式を期待
        if ac_type == "file_exists":
            # 拡張子がなく、パス区切りもない場合は警告
            if "." not in target and "/" not in target and "\\" not in target:
                issues.append(
                    f"file_existsのtarget「{target}」にファイル拡張子または"
                    f"パス区切りがありません"
                )

        # function_defined は関数/クラス名を期待
        if ac_type == "function_defined":
            # スペースのみの名前は不正
            if not re.match(r'^[\w.]+$', target):
                issues.append(
                    f"function_definedのtarget「{target}」が"
                    f"関数/クラス名として不正な形式です"
                )

        return issues

    def _detect_cycles(
        self, graph: Dict[str, List[str]]
    ) -> List[List[str]]:
        """
        依存関係グラフから循環依存を検出する（DFSベース）。

        Args:
            graph: {タスク名: [依存先タスク名, ...]} の辞書

        Returns:
            検出された循環のリスト。各循環は [A, B, C, A] 形式。
        """
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # 循環を検出
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.discard(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles

    def _validate_path_format(self, file_path: str) -> List[str]:
        """
        ファイルパスの形式を検証する。

        Args:
            file_path: 検証対象のファイルパス

        Returns:
            問題があれば警告メッセージのリスト
        """
        issues: List[str] = []

        # 絶対パスは通常不適切（プロジェクト相対パスであるべき）
        if os.path.isabs(file_path):
            issues.append(
                f"パス「{file_path}」が絶対パスです"
                f"（プロジェクト相対パスを推奨）"
            )

        # 不正な文字のチェック
        invalid_chars = set('<>"|?*')
        found_invalid = [c for c in file_path if c in invalid_chars]
        if found_invalid:
            issues.append(
                f"パス「{file_path}」に不正な文字"
                f"「{''.join(found_invalid)}」が含まれています"
            )

        # 連続スラッシュ
        if "//" in file_path or "\\\\" in file_path:
            issues.append(
                f"パス「{file_path}」に連続パス区切りがあります"
            )

        return issues

    def _calculate_score(
        self,
        *,
        task_count: int,
        error_count: int,
        warning_count: int,
        ambiguous_count: int,
        ac_results: List[Dict[str, Any]],
    ) -> float:
        """
        品質スコアを算出する（0.0-1.0）。

        スコアリングルール:
        - ベーススコア: 1.0
        - エラー1件: -0.2
        - 警告1件: -0.05
        - AC未定義タスク1件: -0.15
        - 曖昧表現1件: -0.03
        - 最低スコア: 0.0

        Args:
            task_count: タスク総数
            error_count: エラー数
            warning_count: 警告数
            ambiguous_count: 曖昧表現数
            ac_results: AC検証結果リスト

        Returns:
            品質スコア 0.0-1.0
        """
        if task_count == 0:
            return 0.0

        score = 1.0

        # エラーによる減点
        score -= error_count * 0.2

        # 警告による減点（曖昧表現分は別計算するので除外済み）
        non_ambiguous_warnings = warning_count - ambiguous_count
        score -= max(0, non_ambiguous_warnings) * 0.05

        # 曖昧表現による減点
        score -= ambiguous_count * 0.03

        # AC未定義タスクによる減点
        ac_missing = sum(
            1 for r in ac_results
            if r.get("check") == "ac_exists" and not r.get("passed", True)
        )
        score -= ac_missing * 0.15

        # 範囲制限
        return max(0.0, min(1.0, round(score, 2)))
