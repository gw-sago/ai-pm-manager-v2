#!/usr/bin/env python3
"""
AI PM Framework - Bug Learner Module

タスク失敗（REWORK/REJECTED）からバグパターンを自動学習し、
既存パターンとの類似度判定・新規パターン提案・有効性評価を行う。

Classes:
    BugLearner: バグパターン自動学習エンジン
    EffectivenessEvaluator: バグパターン有効性評価エンジン

Usage:
    from quality.bug_learner import BugLearner, EffectivenessEvaluator

    # 失敗からの自動学習
    learner = BugLearner("AI_PM_PJ")
    result = learner.learn_from_failure("TASK_100", "importエラーが発生", "モジュールX作成")

    # 有効性評価
    evaluator = EffectivenessEvaluator("AI_PM_PJ")
    scores = evaluator.evaluate_all()
"""

import logging
import re
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# カテゴリ判定用キーワードマッピング
_CAUSE_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "import_error": [
        "import", "インポート", "ModuleNotFoundError", "ImportError",
        "モジュール", "module not found", "cannot import",
    ],
    "type_error": [
        "type", "TypeError", "型", "型エラー", "incompatible type",
        "型不一致", "expected", "Incompatible",
    ],
    "logic_error": [
        "logic", "ロジック", "条件", "分岐", "if文", "ループ",
        "無限ループ", "off-by-one", "境界値", "ValueError",
    ],
    "syntax_error": [
        "syntax", "SyntaxError", "構文", "インデント", "indent",
        "括弧", "paren", "セミコロン",
    ],
    "db_error": [
        "sqlite", "database", "DB", "テーブル", "カラム", "SQL",
        "OperationalError", "IntegrityError", "スキーマ", "schema",
        "row", ".get()",
    ],
    "file_error": [
        "file", "ファイル", "FileNotFoundError", "パス", "path",
        "PermissionError", "権限", "ディレクトリ",
    ],
    "state_error": [
        "status", "ステータス", "遷移", "transition", "state",
        "状態", "DONE", "REWORK", "REJECTED", "COMPLETED",
    ],
    "config_error": [
        "config", "設定", "環境変数", "env", "configuration",
        "パラメータ", "parameter",
    ],
    "test_error": [
        "test", "テスト", "assert", "AssertionError", "検証",
        "バリデーション", "validation",
    ],
}

# 影響範囲判定用キーワード
_SCOPE_KEYWORDS: Dict[str, List[str]] = {
    "cross_module": [
        "cross", "複数モジュール", "インターフェース", "interface",
        "依存", "dependency", "連携", "統合", "integration",
    ],
    "module": [
        "module", "モジュール", "パッケージ", "package",
        "クラス全体", "class",
    ],
    "single_file": [
        "file", "ファイル", "関数", "function", "メソッド", "method",
    ],
}

# 重大度推定マッピング
_SEVERITY_MAP: Dict[str, str] = {
    "import_error": "High",
    "type_error": "Medium",
    "logic_error": "High",
    "syntax_error": "Low",
    "db_error": "High",
    "file_error": "Medium",
    "state_error": "Critical",
    "config_error": "Medium",
    "test_error": "Medium",
    "unknown": "Medium",
}


class BugLearner:
    """バグパターン自動学習エンジン

    タスク失敗時のレビューコメントやタスク情報からバグの原因を分析し、
    既存パターンとの照合や新規パターンの提案を行う。

    Attributes:
        project_id: 対象プロジェクトID
    """

    def __init__(self, project_id: str):
        self.project_id = project_id

    def analyze_failure(
        self,
        task_id: str,
        review_comment: str,
        task_title: str = "",
    ) -> dict:
        """タスク失敗（REWORK/REJECTED）時のバグ原因を自動分析

        review_commentからキーワードを抽出し、原因カテゴリ・影響範囲・
        重大度等を推定する。

        Args:
            task_id: 対象タスクID
            review_comment: レビュー時の差し戻しコメント
            task_title: タスクタイトル（補足情報として使用）

        Returns:
            dict: 分析結果
                - cause_category: str - 原因カテゴリ
                - affected_scope: str - 影響範囲
                - related_files: list[str] - 推定される関連ファイル
                - pattern_type: str - 推定されるパターンタイプ
                - description: str - 分析結果の説明
                - severity_estimate: str - 重大度推定
        """
        combined_text = f"{review_comment} {task_title}".lower()

        # 原因カテゴリを推定
        cause_category = self._estimate_cause_category(combined_text)

        # 影響範囲を推定
        affected_scope = self._estimate_scope(combined_text)

        # 関連ファイルを抽出
        related_files = self._extract_file_paths(review_comment)

        # パターンタイプはカテゴリと同じ名称を使用
        pattern_type = cause_category

        # 重大度を推定
        severity_estimate = _SEVERITY_MAP.get(cause_category, "Medium")

        # 説明文を生成
        description = (
            f"タスク {task_id} の失敗分析: "
            f"原因カテゴリ={cause_category}, "
            f"影響範囲={affected_scope}. "
            f"レビューコメント: {review_comment[:200]}"
        )

        return {
            "cause_category": cause_category,
            "affected_scope": affected_scope,
            "related_files": related_files,
            "pattern_type": pattern_type,
            "description": description,
            "severity_estimate": severity_estimate,
        }

    def find_similar_patterns(
        self,
        analysis_result: dict,
        threshold: float = 0.7,
    ) -> list:
        """分析結果と既存バグパターンの類似度を判定

        difflib.SequenceMatcherを使用して、タイトル・説明文・パターンタイプの
        加重平均（title:0.3, description:0.4, pattern_type:0.3）で類似度を算出。

        Args:
            analysis_result: analyze_failure()の戻り値
            threshold: 類似度閾値（デフォルト0.7）

        Returns:
            list[dict]: 類似バグパターンのリスト（類似度降順でソート）
                各要素: {"bug_id": str, "title": str, "similarity": float, ...}
        """
        try:
            from utils.db import get_connection, fetch_all, rows_to_dicts

            conn = get_connection()
            try:
                # ACTIVE + ARCHIVED のパターンを対象にする
                rows = fetch_all(
                    conn,
                    """
                    SELECT id, title, description, pattern_type, severity,
                           solution, status
                    FROM bugs
                    WHERE (project_id = ? OR project_id IS NULL)
                    ORDER BY occurrence_count DESC
                    """,
                    (self.project_id,),
                )
                bugs = rows_to_dicts(rows)
            finally:
                conn.close()

        except Exception as e:
            logger.warning("find_similar_patterns: DB取得エラー: %s", e)
            return []

        # 分析結果のテキスト
        analysis_desc = analysis_result.get("description", "")
        analysis_pattern = analysis_result.get("pattern_type", "")
        # タイトル相当は description の先頭部分を使用
        analysis_title = analysis_result.get("cause_category", "")

        similar: list = []
        for bug in bugs:
            bug_title = bug.get("title", "")
            bug_desc = bug.get("description", "")
            bug_pattern = bug.get("pattern_type", "") or ""

            # 各要素の類似度を算出
            title_sim = SequenceMatcher(
                None, analysis_title, bug_title
            ).ratio()
            desc_sim = SequenceMatcher(
                None, analysis_desc, bug_desc
            ).ratio()
            pattern_sim = SequenceMatcher(
                None, analysis_pattern, bug_pattern
            ).ratio()

            # 加重平均: title(0.3) + description(0.4) + pattern_type(0.3)
            weighted_sim = (
                title_sim * 0.3
                + desc_sim * 0.4
                + pattern_sim * 0.3
            )

            if weighted_sim >= threshold:
                similar.append({
                    "bug_id": bug["id"],
                    "title": bug_title,
                    "similarity": round(weighted_sim, 4),
                    "severity": bug.get("severity", "Medium"),
                    "status": bug.get("status", "ACTIVE"),
                    "pattern_type": bug_pattern,
                    "solution": bug.get("solution", ""),
                })

        # 類似度降順でソート
        similar.sort(key=lambda x: x["similarity"], reverse=True)
        return similar

    def propose_new_pattern(self, analysis_result: dict) -> dict:
        """新規バグパターン登録を提案

        分析結果を基に、bugsテーブルへ登録可能な形式のパターン提案を生成する。

        Args:
            analysis_result: analyze_failure()の戻り値

        Returns:
            dict: 新規パターン提案
                - title: str
                - description: str
                - pattern_type: str
                - severity: str
                - solution: str
                - proposed_id: str ("BUG_NNN" 形式)
        """
        # 次のBUG IDを取得
        proposed_id = self._get_next_bug_id()

        cause = analysis_result.get("cause_category", "unknown")
        desc = analysis_result.get("description", "")
        severity = analysis_result.get("severity_estimate", "Medium")
        scope = analysis_result.get("affected_scope", "single_file")

        title = f"{cause}パターン（自動検出）"
        solution = (
            f"影響範囲: {scope}. "
            f"関連ファイル: {', '.join(analysis_result.get('related_files', []))}"
        )

        return {
            "title": title,
            "description": desc,
            "pattern_type": cause,
            "severity": severity,
            "solution": solution,
            "proposed_id": proposed_id,
        }

    def update_occurrence(self, bug_id: str) -> None:
        """既存パターンの occurrence_count と last_occurred_at を更新

        Args:
            bug_id: 更新対象のバグパターンID
        """
        try:
            from utils.db import get_connection, execute_query

            conn = get_connection()
            try:
                execute_query(
                    conn,
                    """
                    UPDATE bugs
                    SET occurrence_count = occurrence_count + 1,
                        last_occurred_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        datetime.now().isoformat(),
                        datetime.now().isoformat(),
                        bug_id,
                    ),
                )
                conn.commit()
                logger.info(
                    "update_occurrence: %s の occurrence_count を更新",
                    bug_id,
                )
            finally:
                conn.close()

        except Exception as e:
            logger.warning("update_occurrence 失敗 (%s): %s", bug_id, e)

    def learn_from_failure(
        self,
        task_id: str,
        review_comment: str,
        task_title: str = "",
    ) -> dict:
        """メインエントリポイント: 失敗からの自動学習

        analyze_failure -> find_similar_patterns -> update_occurrence
        or propose_new_pattern の一連の処理を実行する。

        Args:
            task_id: 対象タスクID
            review_comment: レビュー時の差し戻しコメント
            task_title: タスクタイトル

        Returns:
            dict:
                - analysis: dict - 分析結果
                - matched_patterns: list - マッチしたパターン
                - new_pattern_proposal: dict or None - 新規パターン提案
                - action_taken: str - 実施アクション
        """
        result: Dict[str, Any] = {
            "analysis": {},
            "matched_patterns": [],
            "new_pattern_proposal": None,
            "action_taken": "error",
        }

        try:
            # Step 1: 分析
            analysis = self.analyze_failure(task_id, review_comment, task_title)
            result["analysis"] = analysis

            # Step 2: 類似パターン検索
            matched = self.find_similar_patterns(analysis)
            result["matched_patterns"] = matched

            if matched:
                # 最も類似度の高いパターンの occurrence を更新
                best_match = matched[0]
                self.update_occurrence(best_match["bug_id"])
                result["action_taken"] = "matched_existing"
                logger.info(
                    "learn_from_failure: 既存パターン %s にマッチ (similarity=%.4f)",
                    best_match["bug_id"],
                    best_match["similarity"],
                )
            else:
                # 新規パターンを提案
                proposal = self.propose_new_pattern(analysis)
                result["new_pattern_proposal"] = proposal
                result["action_taken"] = "proposed_new"
                logger.info(
                    "learn_from_failure: 新規パターン提案 %s",
                    proposal.get("proposed_id", "?"),
                )

        except Exception as e:
            logger.error("learn_from_failure 失敗: %s", e)
            result["action_taken"] = "error"

        return result

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    def _estimate_cause_category(self, text: str) -> str:
        """テキストからバグの原因カテゴリを推定

        各カテゴリのキーワードマッチ数で最もスコアの高いものを選択する。

        Args:
            text: 分析対象テキスト（小文字化済み）

        Returns:
            str: 推定されたカテゴリ名
        """
        scores: Dict[str, int] = {}
        for category, keywords in _CAUSE_CATEGORY_KEYWORDS.items():
            count = sum(1 for kw in keywords if kw.lower() in text)
            if count > 0:
                scores[category] = count

        if not scores:
            return "unknown"

        return max(scores, key=scores.get)  # type: ignore[arg-type]

    def _estimate_scope(self, text: str) -> str:
        """テキストから影響範囲を推定

        Args:
            text: 分析対象テキスト（小文字化済み）

        Returns:
            str: "single_file", "module", or "cross_module"
        """
        for scope, keywords in _SCOPE_KEYWORDS.items():
            if any(kw.lower() in text for kw in keywords):
                return scope
        return "single_file"

    def _extract_file_paths(self, text: str) -> list:
        """テキストからファイルパスを抽出

        一般的なファイルパスパターン（.py, .ts, .js, .sql 等）を正規表現で検出する。

        Args:
            text: 抽出対象テキスト

        Returns:
            list[str]: 検出されたファイルパスのリスト
        """
        # ファイルパスパターン:
        #   - path/to/file.ext
        #   - ./relative/path.py
        #   - scripts/module/file.py
        pattern = r'[\w./\\-]+\.(?:py|ts|tsx|js|jsx|sql|json|md|yaml|yml|toml)'
        matches = re.findall(pattern, text)
        # 重複排除・順序保持
        seen: set = set()
        unique: list = []
        for m in matches:
            if m not in seen:
                seen.add(m)
                unique.append(m)
        return unique

    def _get_next_bug_id(self) -> str:
        """次のBUG IDを算出

        bugsテーブルの既存IDから最大番号を取得し、+1した値を返す。

        Returns:
            str: "BUG_NNN" 形式の次のID
        """
        try:
            from utils.db import get_connection, fetch_one

            conn = get_connection()
            try:
                row = fetch_one(
                    conn,
                    """
                    SELECT id FROM bugs
                    ORDER BY CAST(SUBSTR(id, 5) AS INTEGER) DESC
                    LIMIT 1
                    """,
                )
                if row:
                    # BUG_008 -> 8 -> 9 -> BUG_009
                    current_num = int(row["id"].replace("BUG_", ""))
                    return f"BUG_{current_num + 1:03d}"
                else:
                    return "BUG_001"
            finally:
                conn.close()

        except Exception as e:
            logger.warning("_get_next_bug_id エラー: %s", e)
            return "BUG_999"


class EffectivenessEvaluator:
    """バグパターン有効性評価エンジン

    バグパターンの effectiveness_score を算出し、
    低効果パターンの自動アーカイブを行う。

    Attributes:
        project_id: 対象プロジェクトID（Noneの場合は全プロジェクト）
    """

    def __init__(self, project_id: str = None):
        self.project_id = project_id

    def calculate_score(self, bug_id: str) -> float:
        """バグパターンのeffectiveness_scoreを算出

        算出ロジック:
            effectiveness_score = 1.0 - (related_failures / total_injections)
            total_injections < 5 の場合はデフォルト0.5を返す

        Args:
            bug_id: 対象バグパターンID

        Returns:
            float: 0.0-1.0 の有効性スコア
        """
        try:
            from utils.db import get_connection, fetch_one

            conn = get_connection()
            try:
                row = fetch_one(
                    conn,
                    """
                    SELECT total_injections, related_failures
                    FROM bugs
                    WHERE id = ?
                    """,
                    (bug_id,),
                )
                if row is None:
                    logger.warning(
                        "calculate_score: バグID %s が見つかりません", bug_id
                    )
                    return 0.5

                total_injections = row["total_injections"] or 0
                related_failures = row["related_failures"] or 0

                # サンプル不足時はデフォルト
                if total_injections < 5:
                    return 0.5

                score = 1.0 - (related_failures / total_injections)
                # 0.0-1.0 にクランプ
                return max(0.0, min(1.0, score))

            finally:
                conn.close()

        except Exception as e:
            logger.warning("calculate_score 失敗 (%s): %s", bug_id, e)
            return 0.5

    def evaluate_all(self) -> list:
        """全ACTIVEパターンの有効性を一括評価

        各パターンの effectiveness_score を再計算し、DBを更新する。

        Returns:
            list[dict]: 評価結果のリスト
                各要素: {"bug_id": str, "old_score": float, "new_score": float, ...}
        """
        results: list = []
        try:
            from utils.db import (
                get_connection, fetch_all, execute_query, rows_to_dicts,
            )

            conn = get_connection()
            try:
                rows = fetch_all(
                    conn,
                    """
                    SELECT id, effectiveness_score, total_injections,
                           related_failures
                    FROM bugs
                    WHERE status = 'ACTIVE'
                    ORDER BY id
                    """,
                )
                bugs = rows_to_dicts(rows)

                for bug in bugs:
                    bug_id = bug["id"]
                    old_score = bug.get("effectiveness_score", 0.5) or 0.5
                    total = bug.get("total_injections", 0) or 0
                    failures = bug.get("related_failures", 0) or 0

                    # スコア算出
                    if total < 5:
                        new_score = 0.5
                    else:
                        new_score = max(
                            0.0, min(1.0, 1.0 - (failures / total))
                        )

                    # DB更新
                    execute_query(
                        conn,
                        """
                        UPDATE bugs
                        SET effectiveness_score = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (new_score, datetime.now().isoformat(), bug_id),
                    )

                    results.append({
                        "bug_id": bug_id,
                        "old_score": round(old_score, 4),
                        "new_score": round(new_score, 4),
                        "total_injections": total,
                        "related_failures": failures,
                    })

                conn.commit()
                logger.info(
                    "evaluate_all: %d パターンを評価完了", len(results)
                )

            finally:
                conn.close()

        except Exception as e:
            logger.error("evaluate_all 失敗: %s", e)

        return results

    def deactivate_low_effectiveness(
        self,
        threshold: float = 0.2,
        min_samples: int = 10,
    ) -> list:
        """低効果パターンを自動非アクティブ化（ACTIVE -> ARCHIVED）

        effectiveness_score が threshold 以下で、かつ
        total_injections が min_samples 以上のパターンを ARCHIVED に変更する。

        Args:
            threshold: 非アクティブ化閾値（デフォルト0.2）
            min_samples: 最低評価母数（デフォルト10）

        Returns:
            list[str]: 非アクティブ化されたbug_idのリスト
        """
        deactivated: list = []
        try:
            from utils.db import get_connection, fetch_all, execute_query, rows_to_dicts

            conn = get_connection()
            try:
                rows = fetch_all(
                    conn,
                    """
                    SELECT id, effectiveness_score, total_injections
                    FROM bugs
                    WHERE status = 'ACTIVE'
                      AND total_injections >= ?
                      AND effectiveness_score <= ?
                    ORDER BY effectiveness_score ASC
                    """,
                    (min_samples, threshold),
                )
                candidates = rows_to_dicts(rows)

                for bug in candidates:
                    bug_id = bug["id"]
                    execute_query(
                        conn,
                        """
                        UPDATE bugs
                        SET status = 'ARCHIVED',
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (datetime.now().isoformat(), bug_id),
                    )
                    deactivated.append(bug_id)
                    logger.info(
                        "deactivate: %s をARCHIVEDに変更 "
                        "(score=%.4f, injections=%d)",
                        bug_id,
                        bug.get("effectiveness_score", 0),
                        bug.get("total_injections", 0),
                    )

                conn.commit()

            finally:
                conn.close()

        except Exception as e:
            logger.error("deactivate_low_effectiveness 失敗: %s", e)

        return deactivated

    def record_injection(self, bug_id: str) -> None:
        """バグパターン注入を記録（total_injections++）

        Worker実行時にバグパターンがプロンプトに注入されたことを記録する。

        Args:
            bug_id: 対象バグパターンID
        """
        try:
            from utils.db import get_connection, execute_query

            conn = get_connection()
            try:
                execute_query(
                    conn,
                    """
                    UPDATE bugs
                    SET total_injections = total_injections + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (datetime.now().isoformat(), bug_id),
                )
                conn.commit()
                logger.debug("record_injection: %s", bug_id)
            finally:
                conn.close()

        except Exception as e:
            logger.warning("record_injection 失敗 (%s): %s", bug_id, e)

    def record_failure(self, bug_id: str) -> None:
        """バグパターン関連の失敗を記録（related_failures++）

        バグパターンが注入されたにもかかわらず同種の失敗が発生した場合に記録する。

        Args:
            bug_id: 対象バグパターンID
        """
        try:
            from utils.db import get_connection, execute_query

            conn = get_connection()
            try:
                execute_query(
                    conn,
                    """
                    UPDATE bugs
                    SET related_failures = related_failures + 1,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (datetime.now().isoformat(), bug_id),
                )
                conn.commit()
                logger.debug("record_failure: %s", bug_id)
            finally:
                conn.close()

        except Exception as e:
            logger.warning("record_failure 失敗 (%s): %s", bug_id, e)
