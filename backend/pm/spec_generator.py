#!/usr/bin/env python3
"""
AI PM Framework - Spec Generator

ORDERゴール・要件からタスク候補を自動抽出し、
機械検証可能な Acceptance Criteria を生成するモジュール。

Usage (standalone):
    from pm.spec_generator import SpecGenerator

    gen = SpecGenerator()
    prompt = gen.enhance_prompt(order_content)
    criteria = gen.generate_acceptance_criteria(task_def)

Integration with process_order.py:
    SpecGenerator.enhance_prompt() を使ってAIプロンプトを改善し、
    Acceptance Criteria をJSON出力に含めるようにする。
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# --- AC Type Definitions ---
# 機械検証可能な Acceptance Criteria のタイプ
AC_TYPES = (
    "file_exists",
    "function_defined",
    "test_passes",
    "import_works",
    "output_contains",
)


class SpecGeneratorError(Exception):
    """SpecGenerator 処理エラー"""
    pass


class SpecGenerator:
    """
    ORDER内容からタスク仕様を生成し、
    機械検証可能な Acceptance Criteria を付与するジェネレータ。

    Attributes:
        ac_type_hints: ACタイプごとのキーワードヒント（推論に使用）
    """

    def __init__(self, *, ac_type_hints: Optional[Dict[str, List[str]]] = None):
        """
        Args:
            ac_type_hints: ACタイプ推論用のキーワードヒント。
                           None の場合はデフォルトを使用。
                           (BUG_001対策: ミュータブルデフォルト引数を回避)
        """
        if ac_type_hints is not None:
            self.ac_type_hints = ac_type_hints
        else:
            self.ac_type_hints = {
                "file_exists": [
                    "作成", "生成", "ファイル", "create", "file", "write",
                    "出力", "output", "save", "保存", "新規",
                ],
                "function_defined": [
                    "関数", "メソッド", "クラス", "function", "method", "class",
                    "def", "実装", "implement", "定義", "define",
                ],
                "test_passes": [
                    "テスト", "test", "検証", "verify", "確認", "assert",
                    "pytest", "unittest", "品質",
                ],
                "import_works": [
                    "モジュール", "module", "import", "インポート", "パッケージ",
                    "package", "ライブラリ", "library",
                ],
                "output_contains": [
                    "出力", "表示", "output", "print", "ログ", "log",
                    "含む", "contain", "結果", "result", "レスポンス",
                ],
            }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enhance_prompt(self, order_content: str) -> str:
        """
        AIプロンプトを改善し、Acceptance Criteria を JSON 出力に含めるよう指示する。

        既存の process_order.py の _build_requirements_prompt() に相当するが、
        各タスクに acceptance_criteria フィールドを追加する点が異なる。

        Args:
            order_content: ORDER.md のテキスト内容

        Returns:
            AI に渡す改善済みプロンプト文字列
        """
        if not order_content or not order_content.strip():
            raise SpecGeneratorError("ORDER内容が空です")

        return f"""【重要】以下のORDER内容のみを分析してJSON形式で出力してください。
ファイルを探したり、質問したりせず、与えられた情報だけで要件定義を作成してください。

## 分析対象ORDER内容
```markdown
{order_content}
```

## 必須出力形式（JSONのみ、他の文章は禁止）
```json
{{
  "goal": {{
    "summary": "ゴールの要約（1-2文）",
    "objectives": ["目標1", "目標2"],
    "success_criteria": ["成功基準1", "成功基準2"]
  }},
  "requirements": {{
    "functional": ["機能要件1", "機能要件2"],
    "non_functional": ["非機能要件1"],
    "constraints": ["制約事項1"]
  }},
  "tasks": [
    {{
      "title": "タスク名",
      "description": "タスク説明",
      "priority": "P0",
      "model": "Sonnet",
      "depends_on": [],
      "target_files": ["path/to/file1.py", "path/to/file2.py"],
      "acceptance_criteria": [
        {{
          "criterion": "何が満たされるべきかの説明",
          "type": "file_exists|function_defined|test_passes|import_works|output_contains",
          "target": "検証対象（ファイルパス、関数名、テスト名など）"
        }}
      ]
    }}
  ]
}}
```

## Acceptance Criteria ルール
- 各タスクに最低1つ、最大5つのacceptance_criteriaを含めること
- typeは以下の5種類のいずれかを使用:
  - "file_exists": 指定ファイルが存在する（target=ファイルパス）
  - "function_defined": 指定の関数/クラスが定義されている（target=モジュール.関数名）
  - "test_passes": 指定テストが通過する（target=テストファイルパスまたはテスト関数名）
  - "import_works": 指定モジュールがインポート可能（target=モジュールパス）
  - "output_contains": 実行結果に指定文字列を含む（target=期待文字列）
- criterionは日本語で具体的に記述（「ファイルXが存在する」「関数Yが定義されている」等）
- targetは機械的に検証できる具体的な値を指定

【出力ルール】
- JSONのみを出力（説明文、質問、確認は一切不要）
- 上記ORDER内容から要件を抽出してタスク分解する
- tasksは実装に必要な具体的作業を2-5個程度に分割
- target_filesには各タスクが変更対象とするファイルパスを配列で指定（省略可能）
- 各タスクにacceptance_criteriaを必ず含めること"""

    def generate_acceptance_criteria(self, task_def: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        タスク定義から機械検証可能な Acceptance Criteria を生成する。

        AI が acceptance_criteria を返さなかった場合や、
        既存タスクに AC を追加したい場合に使用する。
        タスクの title, description, target_files から AC を推論する。

        Args:
            task_def: タスク定義辞書。以下のキーを参照:
                - title (str): タスク名
                - description (str): タスク説明
                - target_files (list[str]): 対象ファイルパス一覧

        Returns:
            AC エントリのリスト。各エントリは:
                {"criterion": str, "type": str, "target": str}
        """
        criteria: List[Dict[str, str]] = []

        title = task_def.get("title", "") or ""
        description = task_def.get("description", "") or ""
        target_files = task_def.get("target_files") or []

        # テキストを結合して分析用に使用
        combined_text = f"{title} {description}".lower()

        # --- 1. target_files からファイル存在ACを生成 ---
        for file_path in target_files:
            criteria.append({
                "criterion": f"ファイル {file_path} が存在する",
                "type": "file_exists",
                "target": file_path,
            })

        # --- 2. ファイルパスから関数/クラス定義ACを推論 ---
        for file_path in target_files:
            if file_path.endswith(".py"):
                module_name = self._path_to_module_name(file_path)
                if module_name:
                    criteria.append({
                        "criterion": f"モジュール {module_name} がインポート可能である",
                        "type": "import_works",
                        "target": module_name,
                    })

        # --- 3. テキスト分析による追加AC ---
        # 「テスト」関連のキーワードがあればテストACを追加
        if self._text_matches_type(combined_text, "test_passes"):
            test_targets = self._extract_test_targets(target_files, description)
            for test_target in test_targets:
                criteria.append({
                    "criterion": f"テスト {test_target} が通過する",
                    "type": "test_passes",
                    "target": test_target,
                })

        # 関数/クラス定義のキーワードがあれば
        if self._text_matches_type(combined_text, "function_defined"):
            func_targets = self._extract_function_targets(description, title)
            for func_target in func_targets:
                criteria.append({
                    "criterion": f"{func_target} が定義されている",
                    "type": "function_defined",
                    "target": func_target,
                })

        # --- 4. AC が空の場合のフォールバック ---
        if not criteria:
            criteria.append({
                "criterion": f"タスク「{title}」の成果物が作成されている",
                "type": "output_contains",
                "target": title,
            })

        # 重複を除去（targetベース）
        seen_targets: set = set()
        unique_criteria: List[Dict[str, str]] = []
        for ac in criteria:
            key = (ac["type"], ac["target"])
            if key not in seen_targets:
                seen_targets.add(key)
                unique_criteria.append(ac)

        return unique_criteria

    def merge_acceptance_criteria(
        self,
        ai_criteria: Optional[List[Dict[str, str]]],
        generated_criteria: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        AI生成のACと推論生成のACをマージする。

        AI生成のACを優先し、推論生成のACで補完する。
        重複はtargetベースで除去する。

        Args:
            ai_criteria: AI が生成した AC リスト（None 可）
            generated_criteria: generate_acceptance_criteria() で生成した AC リスト

        Returns:
            マージ済み AC リスト
        """
        if ai_criteria is None:
            ai_criteria = []

        # AI生成分を先に追加
        merged: List[Dict[str, str]] = []
        seen_targets: set = set()

        for ac in ai_criteria:
            # バリデーション: 必須フィールド確認
            if not self._validate_ac_entry(ac):
                logger.warning(f"不正なAC エントリをスキップ: {ac}")
                continue
            key = (ac["type"], ac["target"])
            if key not in seen_targets:
                seen_targets.add(key)
                merged.append(ac)

        # 推論生成分で補完
        for ac in generated_criteria:
            key = (ac["type"], ac["target"])
            if key not in seen_targets:
                seen_targets.add(key)
                merged.append(ac)

        return merged

    def format_acceptance_criteria_markdown(
        self, criteria: List[Dict[str, str]]
    ) -> str:
        """
        AC リストを Markdown 形式にフォーマットする。

        TASK_XXX.md に埋め込む「## Acceptance Criteria」セクション用。

        Args:
            criteria: AC エントリのリスト

        Returns:
            Markdown 形式の文字列
        """
        if not criteria:
            return "（Acceptance Criteria なし）\n"

        lines: List[str] = []
        type_labels = {
            "file_exists": "ファイル存在",
            "function_defined": "関数/クラス定義",
            "test_passes": "テスト通過",
            "import_works": "インポート可能",
            "output_contains": "出力確認",
        }

        for i, ac in enumerate(criteria, 1):
            ac_type = ac.get("type", "unknown")
            label = type_labels.get(ac_type, ac_type)
            criterion = ac.get("criterion", "（未定義）")
            target = ac.get("target", "（未定義）")

            lines.append(f"- [ ] **AC-{i}** [{label}] {criterion}")
            lines.append(f"  - 検証対象: `{target}`")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _text_matches_type(self, text: str, ac_type: str) -> bool:
        """テキストが指定ACタイプのキーワードを含むか判定"""
        hints = self.ac_type_hints.get(ac_type, [])
        return any(hint in text for hint in hints)

    def _path_to_module_name(self, file_path: str) -> Optional[str]:
        """ファイルパスを Python モジュール名に変換する"""
        if not file_path.endswith(".py"):
            return None

        # __init__.py は親ディレクトリをモジュール名とする
        path = Path(file_path)
        if path.name == "__init__.py":
            parts = path.parent.parts
        else:
            # .py を除いてパス部分をモジュール名に
            parts = list(path.parent.parts) + [path.stem]

        if not parts:
            return None

        # "backend/pm/spec_generator.py" -> "pm.spec_generator" のように
        # aipm-db 以降を取り出す（プロジェクト構造に依存しないフォールバックも用意）
        module_parts = list(parts)

        # "backend/" プレフィックスを除去
        for prefix in (["scripts", "aipm-db"], ["scripts", "aipm_db"]):
            if len(module_parts) > len(prefix):
                match = True
                for a, b in zip(module_parts[:len(prefix)], prefix):
                    if a.replace("-", "_") != b.replace("-", "_"):
                        match = False
                        break
                if match:
                    module_parts = module_parts[len(prefix):]
                    break

        return ".".join(module_parts) if module_parts else None

    def _extract_test_targets(
        self, target_files: List[str], description: str
    ) -> List[str]:
        """テスト対象を target_files や description から抽出"""
        targets: List[str] = []

        # target_files からテストファイルを抽出
        for fp in target_files:
            name = Path(fp).name
            if name.startswith("test_") or name.endswith("_test.py"):
                targets.append(fp)

        # description から "test_xxx" パターンを抽出
        test_pattern = re.compile(r'\btest_\w+', re.IGNORECASE)
        for match in test_pattern.finditer(description):
            candidate = match.group()
            if candidate not in targets:
                targets.append(candidate)

        return targets

    def _extract_function_targets(
        self, description: str, title: str
    ) -> List[str]:
        """関数/クラス名を description と title から抽出"""
        targets: List[str] = []
        combined = f"{title} {description}"

        # Python 関数名パターン: xxx_yyy() や ClassName 形式
        func_pattern = re.compile(r'\b([a-z_][a-z0-9_]*)\s*\(', re.IGNORECASE)
        for match in func_pattern.finditer(combined):
            name = match.group(1)
            # 一般的すぎるワードを除外
            if name not in ("if", "for", "while", "def", "class", "return",
                            "print", "get", "set", "str", "int", "list",
                            "dict", "type", "len", "range", "open"):
                if name not in targets:
                    targets.append(name)

        # CamelCase クラス名パターン
        class_pattern = re.compile(r'\b([A-Z][a-zA-Z0-9]+)\b')
        for match in class_pattern.finditer(combined):
            name = match.group(1)
            # 一般的な英単語を除外（3文字以下やよく使う名詞）
            if len(name) > 3 and name not in (
                "ORDER", "TASK", "JSON", "True", "False", "None",
                "Python", "Markdown", "Worker", "Sonnet",
            ):
                if name not in targets:
                    targets.append(name)

        return targets

    @staticmethod
    def _validate_ac_entry(ac: Dict[str, Any]) -> bool:
        """AC エントリが有効か検証する"""
        if not isinstance(ac, dict):
            return False

        required_keys = ("criterion", "type", "target")
        for key in required_keys:
            if key not in ac or not ac[key]:
                return False

        # type が有効値か
        if ac["type"] not in AC_TYPES:
            logger.warning(
                f"不明な AC type: {ac['type']}（許可値: {AC_TYPES}）"
            )
            return False

        return True
