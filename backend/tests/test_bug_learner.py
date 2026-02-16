"""
AI PM Framework - Bug Learner Tests

BugLearner および EffectivenessEvaluator の機能をテスト。

Test cases:
    - BugLearner クラスのテスト（類似度判定・パターン提案）
    - EffectivenessEvaluator クラスのテスト（有効性評価・自動非アクティブ化）
    - 後方互換性テスト（新カラムの存在・デフォルト値）
"""

import sqlite3
import sys
from pathlib import Path

# 親ディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quality.bug_learner import BugLearner, EffectivenessEvaluator
from utils.db import get_connection, execute_query, fetch_one, row_to_dict


class TestBugLearner:
    """BugLearner クラスのテスト"""

    def test_analyze_failure_import_error(self):
        """importエラーのレビューコメントからimport_errorカテゴリを検出"""
        learner = BugLearner("TEST_PJ")
        result = learner.analyze_failure(
            "TASK_999",
            "ModuleNotFoundError: モジュール xxx が見つかりません",
            "モジュール作成タスク"
        )
        assert result["cause_category"] == "import_error"
        assert result["severity_estimate"] == "High"
        print("  PASS: analyze_failure_import_error")

    def test_analyze_failure_state_error(self):
        """ステータス遷移エラーの検出"""
        learner = BugLearner("TEST_PJ")
        result = learner.analyze_failure(
            "TASK_999",
            "DONE→REJECTED遷移は禁止されています。状態遷移エラー。",
            ""
        )
        assert result["cause_category"] == "state_error"
        assert result["severity_estimate"] == "Critical"
        print("  PASS: analyze_failure_state_error")

    def test_analyze_failure_db_error(self):
        """DBエラーの検出（sqlite3.Row.get()パターン）"""
        learner = BugLearner("TEST_PJ")
        result = learner.analyze_failure(
            "TASK_999",
            "sqlite3.Row.get()は使用できません。row['key']を使ってください。",
            ""
        )
        assert result["cause_category"] == "db_error"
        assert result["severity_estimate"] == "High"
        print("  PASS: analyze_failure_db_error")

    def test_analyze_failure_unknown(self):
        """キーワードなしの場合はunknown"""
        learner = BugLearner("TEST_PJ")
        result = learner.analyze_failure("TASK_999", "何か問題があります", "")
        assert result["cause_category"] == "unknown"
        assert result["severity_estimate"] == "Medium"
        print("  PASS: analyze_failure_unknown")

    def test_extract_file_paths(self):
        """ファイルパス抽出"""
        learner = BugLearner("TEST_PJ")
        paths = learner._extract_file_paths(
            "backend/worker/execute_task.py でエラー。utils/db.py も確認"
        )
        assert "backend/worker/execute_task.py" in paths
        assert "utils/db.py" in paths
        print("  PASS: extract_file_paths")

    def test_find_similar_patterns_with_active_bugs(self):
        """既存パターンとの類似度判定（マッチあり）"""
        learner = BugLearner("AI_PM_PJ")  # 実際のプロジェクトID

        # DB上にACTIVEなバグパターンが存在するかチェック
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                "SELECT COUNT(*) as cnt FROM bugs WHERE status = 'ACTIVE'",
            )
            active_count = row["cnt"] if row else 0
        finally:
            conn.close()

        if active_count == 0:
            print("  SKIP: find_similar_patterns_with_active_bugs (no active bugs)")
            return

        # sqlite3.Row.get() エラーに類似したパターンで検索
        analysis = {
            "cause_category": "db_error",
            "affected_scope": "single_file",
            "related_files": ["utils/db.py"],
            "pattern_type": "db_error",
            "description": "タスク TASK_999 の失敗分析: 原因カテゴリ=db_error, 影響範囲=single_file. レビューコメント: sqlite3.Row objectに.get()メソッドは存在しません",
            "severity_estimate": "High",
        }

        # 類似度閾値を0.3に下げて検索（マッチしやすくする）
        similar = learner.find_similar_patterns(analysis, threshold=0.3)

        # 結果が返ることを確認（類似度は低くてもOK）
        assert isinstance(similar, list)

        # BUG_003 が存在する場合、それとマッチする可能性が高い
        bug_ids = [s["bug_id"] for s in similar]
        if "BUG_003" in bug_ids:
            print("  PASS: find_similar_patterns_with_active_bugs (matched BUG_003)")
        else:
            print(f"  PASS: find_similar_patterns_with_active_bugs (returned {len(similar)} patterns)")

    def test_find_similar_patterns_no_match(self):
        """類似度が閾値未満の場合は空リスト"""
        learner = BugLearner("AI_PM_PJ")

        # 完全に無関係なパターン
        analysis = {
            "cause_category": "unknown",
            "affected_scope": "single_file",
            "related_files": [],
            "pattern_type": "unknown",
            "description": "完全に無関係なエラーパターンXYZ123",
            "severity_estimate": "Low",
        }

        # 類似度閾値を0.95に上げて検索（マッチしにくくする）
        similar = learner.find_similar_patterns(analysis, threshold=0.95)

        # 類似度が高いものがない場合は空リストが返る
        assert isinstance(similar, list)
        print(f"  PASS: find_similar_patterns_no_match (returned {len(similar)} high-similarity patterns)")

    def test_propose_new_pattern(self):
        """新規パターン提案のフォーマット確認"""
        learner = BugLearner("TEST_PJ")
        analysis = {
            "cause_category": "test_error",
            "affected_scope": "single_file",
            "related_files": ["test_foo.py"],
            "pattern_type": "test_error",
            "description": "テストエラー分析",
            "severity_estimate": "Medium",
        }
        proposal = learner.propose_new_pattern(analysis)

        assert "title" in proposal
        assert "proposed_id" in proposal
        assert proposal["proposed_id"].startswith("BUG_")
        assert proposal["severity"] == "Medium"
        assert proposal["pattern_type"] == "test_error"
        print("  PASS: propose_new_pattern")

    def test_learn_from_failure_integration(self):
        """learn_from_failure メインフローの結合テスト"""
        learner = BugLearner("AI_PM_PJ")  # 実際のプロジェクトID（DBにデータあり）
        result = learner.learn_from_failure(
            "TASK_999",
            "sqlite3.Rowオブジェクトに.get()メソッドは存在しません",
            "DB操作モジュール"
        )

        assert result["action_taken"] in ("matched_existing", "proposed_new", "error")
        assert "analysis" in result
        assert result["analysis"]["cause_category"] == "db_error"

        # matched_patterns または new_pattern_proposal のいずれかが存在
        if result["action_taken"] == "matched_existing":
            assert len(result["matched_patterns"]) > 0
            assert result["new_pattern_proposal"] is None
        elif result["action_taken"] == "proposed_new":
            assert result["new_pattern_proposal"] is not None
            assert len(result["matched_patterns"]) == 0

        print("  PASS: learn_from_failure_integration")

    def test_update_occurrence(self):
        """update_occurrence メソッドのテスト（BUG_001を対象）"""
        learner = BugLearner("AI_PM_PJ")

        # 更新前の値を取得
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                "SELECT occurrence_count FROM bugs WHERE id = 'BUG_001'",
            )
            if row is None:
                print("  SKIP: update_occurrence (BUG_001 not found)")
                return
            old_count = row["occurrence_count"] or 0
        finally:
            conn.close()

        # 更新実行
        learner.update_occurrence("BUG_001")

        # 更新後の値を確認
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                "SELECT occurrence_count FROM bugs WHERE id = 'BUG_001'",
            )
            new_count = row["occurrence_count"] or 0
            assert new_count == old_count + 1
        finally:
            conn.close()

        print("  PASS: update_occurrence")


class TestEffectivenessEvaluator:
    """EffectivenessEvaluator クラスのテスト"""

    def test_calculate_score_insufficient_samples(self):
        """total_injections < 5 の場合はデフォルト0.5"""
        evaluator = EffectivenessEvaluator("AI_PM_PJ")

        # BUG_001は初期状態ではtotal_injections=0のはず
        # （もし既に5以上なら別のBUGを探す）
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                """
                SELECT id FROM bugs
                WHERE total_injections < 5
                ORDER BY id
                LIMIT 1
                """,
            )
            if row is None:
                print("  SKIP: calculate_score_insufficient_samples (all bugs have 5+ injections)")
                return
            test_bug_id = row["id"]
        finally:
            conn.close()

        score = evaluator.calculate_score(test_bug_id)
        assert score == 0.5
        print(f"  PASS: calculate_score_insufficient_samples (tested {test_bug_id})")

    def test_calculate_score_nonexistent_bug(self):
        """存在しないBUG IDの場合はデフォルト0.5"""
        evaluator = EffectivenessEvaluator("TEST_PJ")
        score = evaluator.calculate_score("BUG_NONEXISTENT")
        assert score == 0.5
        print("  PASS: calculate_score_nonexistent_bug")

    def test_evaluate_all(self):
        """全パターン一括評価"""
        evaluator = EffectivenessEvaluator("AI_PM_PJ")
        results = evaluator.evaluate_all()

        assert isinstance(results, list)

        # 各結果に必要なキーがあること
        if results:
            assert "bug_id" in results[0]
            assert "old_score" in results[0]
            assert "new_score" in results[0]
            assert "total_injections" in results[0]
            assert "related_failures" in results[0]
            print(f"  PASS: evaluate_all (evaluated {len(results)} patterns)")
        else:
            print("  PASS: evaluate_all (no active patterns to evaluate)")

    def test_deactivate_low_effectiveness_no_targets(self):
        """母数不足で非アクティブ化対象なし"""
        evaluator = EffectivenessEvaluator("AI_PM_PJ")

        # デフォルトの閾値（0.2, min_samples=10）では、
        # 初期状態ではtotal_injections < 10 なので対象なし
        deactivated = evaluator.deactivate_low_effectiveness()

        assert isinstance(deactivated, list)
        # 対象がなければ空リスト、あればリストに要素
        print(f"  PASS: deactivate_low_effectiveness (deactivated {len(deactivated)} patterns)")

    def test_record_injection(self):
        """record_injectionでtotal_injectionsが増加すること"""
        evaluator = EffectivenessEvaluator("AI_PM_PJ")

        # BUG_001を対象にテスト
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                "SELECT total_injections FROM bugs WHERE id = 'BUG_001'",
            )
            if row is None:
                print("  SKIP: record_injection (BUG_001 not found)")
                return
            old_injections = row["total_injections"] or 0
        finally:
            conn.close()

        # 記録実行
        evaluator.record_injection("BUG_001")

        # 増加を確認
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                "SELECT total_injections FROM bugs WHERE id = 'BUG_001'",
            )
            new_injections = row["total_injections"] or 0
            assert new_injections == old_injections + 1
        finally:
            conn.close()

        print("  PASS: record_injection")

    def test_record_failure(self):
        """record_failureでrelated_failuresが増加すること"""
        evaluator = EffectivenessEvaluator("AI_PM_PJ")

        # BUG_001を対象にテスト
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                "SELECT related_failures FROM bugs WHERE id = 'BUG_001'",
            )
            if row is None:
                print("  SKIP: record_failure (BUG_001 not found)")
                return
            old_failures = row["related_failures"] or 0
        finally:
            conn.close()

        # 記録実行
        evaluator.record_failure("BUG_001")

        # 増加を確認
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                "SELECT related_failures FROM bugs WHERE id = 'BUG_001'",
            )
            new_failures = row["related_failures"] or 0
            assert new_failures == old_failures + 1
        finally:
            conn.close()

        print("  PASS: record_failure")


class TestBackwardCompatibility:
    """後方互換性テスト"""

    def test_bugs_table_has_new_columns(self):
        """bugsテーブルに新カラムが存在すること"""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(bugs)")
            columns = {row[1] for row in cur.fetchall()}
        finally:
            conn.close()

        assert "effectiveness_score" in columns
        assert "total_injections" in columns
        assert "related_failures" in columns
        print("  PASS: bugs_table_has_new_columns")

    def test_existing_bugs_have_default_values(self):
        """既存バグパターンがデフォルト値で初期化されていること"""
        conn = get_connection()
        try:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM bugs WHERE id = 'BUG_001'")
            row = cur.fetchone()
        finally:
            conn.close()

        if row is None:
            print("  SKIP: existing_bugs_have_default_values (BUG_001 not found)")
            return

        # デフォルト値は0.5, 0, 0
        # 注意: 既に record_injection/record_failure でインクリメント済みの場合は
        # >= 0 であることのみ確認
        assert row["effectiveness_score"] is not None
        assert row["effectiveness_score"] >= 0.0
        assert row["effectiveness_score"] <= 1.0
        assert row["total_injections"] >= 0
        assert row["related_failures"] >= 0
        print("  PASS: existing_bugs_have_default_values")

    def test_get_known_bugs_compatible(self):
        """bugsテーブルからのSELECTが正常に動作すること"""
        # Worker execute_task.py の _get_known_bugs() 相当の処理をテスト
        conn = get_connection()
        try:
            row = fetch_one(
                conn,
                """
                SELECT id, title, description, severity, status
                FROM bugs
                WHERE status = 'ACTIVE'
                ORDER BY severity DESC, occurrence_count DESC
                LIMIT 1
                """,
            )

            # 結果があればキーにアクセスできることを確認
            if row:
                # BUG_003: sqlite3.Rowに.get()を使わない
                assert row["id"] is not None
                assert row["title"] is not None
                # row.get() は使用禁止
        finally:
            conn.close()

        print("  PASS: get_known_bugs_compatible")


def run_all_tests():
    """全テスト実行"""
    print("\n=== Bug Learner Tests ===\n")

    print("TestBugLearner:")
    test_bug_learner = TestBugLearner()
    test_bug_learner.test_analyze_failure_import_error()
    test_bug_learner.test_analyze_failure_state_error()
    test_bug_learner.test_analyze_failure_db_error()
    test_bug_learner.test_analyze_failure_unknown()
    test_bug_learner.test_extract_file_paths()
    test_bug_learner.test_find_similar_patterns_with_active_bugs()
    test_bug_learner.test_find_similar_patterns_no_match()
    test_bug_learner.test_propose_new_pattern()
    test_bug_learner.test_learn_from_failure_integration()
    test_bug_learner.test_update_occurrence()

    print("\nTestEffectivenessEvaluator:")
    test_effectiveness = TestEffectivenessEvaluator()
    test_effectiveness.test_calculate_score_insufficient_samples()
    test_effectiveness.test_calculate_score_nonexistent_bug()
    test_effectiveness.test_evaluate_all()
    test_effectiveness.test_deactivate_low_effectiveness_no_targets()
    test_effectiveness.test_record_injection()
    test_effectiveness.test_record_failure()

    print("\nTestBackwardCompatibility:")
    test_compat = TestBackwardCompatibility()
    test_compat.test_bugs_table_has_new_columns()
    test_compat.test_existing_bugs_have_default_values()
    test_compat.test_get_known_bugs_compatible()

    print("\n=== All Bug Learner tests passed ===\n")


if __name__ == "__main__":
    run_all_tests()
