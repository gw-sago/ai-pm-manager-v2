#!/usr/bin/env python3
"""
AI PM Framework - AI質問検知ロジック

claude -p（または claude -c）の出力から質問パターンを検知し、
Interactionを作成してタスクをWAITING_INPUT状態にする

Usage:
    # モジュールとして使用
    from interaction.detect import QuestionDetector
    detector = QuestionDetector(project_id, task_id)
    result = detector.analyze_output(claude_output)

    # コマンドラインから手動テスト
    python backend/interaction/detect.py PROJECT_ID TASK_ID --text "質問テキスト"
    python backend/interaction/detect.py PROJECT_ID TASK_ID --file output.txt
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import (
    get_connection,
    transaction,
    execute_query,
    fetch_one,
    row_to_dict,
    DatabaseError,
)
from utils.validation import (
    validate_project_name,
    validate_task_id,
    project_exists,
    task_exists,
    ValidationError,
)
from utils.transition import (
    record_transition,
    TransitionError,
)


# ========================================
# 質問検知パターン定義
# ========================================

# 直接質問パターン（日本語・英語）
QUESTION_PATTERNS = [
    # 日本語の質問パターン
    r"[？?]$",                           # 末尾が「？」で終わる
    r"ですか[？?]?$",                    # 「〜ですか？」
    r"でしょうか[？?]?$",                # 「〜でしょうか？」
    r"しますか[？?]?$",                  # 「〜しますか？」
    r"どうしますか",                     # 「どうしますか」
    r"どちらを",                         # 「どちらを〜」
    r"どれを",                           # 「どれを〜」
    r"何を",                             # 「何を〜」
    r"選択してください",                 # 選択を求める
    r"お選びください",                   # 選択を求める
    r"教えてください",                   # 情報を求める
    r"指定してください",                 # 指定を求める
    r"確認してください",                 # 確認を求める
    r"ご確認ください",                   # 確認を求める
    r"お知らせください",                 # 情報を求める
    r"ご指示ください",                   # 指示を求める

    # 英語の質問パターン
    r"\?$",                              # 末尾が「?」で終わる
    r"please select",                    # 選択を求める
    r"please choose",                    # 選択を求める
    r"please confirm",                   # 確認を求める
    r"please specify",                   # 指定を求める
    r"would you like",                   # 確認を求める
    r"do you want",                      # 確認を求める
    r"should i",                         # 確認を求める
    r"shall i",                          # 確認を求める
    r"which (one|option)",               # 選択を求める
    r"what should",                      # 指示を求める
]

# AskUserQuestion パターン（Claude Code の質問形式）
ASK_USER_PATTERNS = [
    r"AskUserQuestion",                  # Claude Code の質問ツール使用
    r'"questions"\s*:\s*\[',             # JSON形式の質問
    r'"header"\s*:\s*"',                 # 質問ヘッダー
    r'"options"\s*:\s*\[',               # 選択肢
]

# 確認待ちパターン
CONFIRMATION_PATTERNS = [
    r"続行しますか",
    r"よろしいですか",
    r"実行しますか",
    r"削除しますか",
    r"変更しますか",
    r"作成しますか",
    r"continue\??",
    r"proceed\??",
    r"confirm\??",
    r"\[y/n\]",
    r"\[yes/no\]",
]

# 入力待ちパターン
INPUT_WAIT_PATTERNS = [
    r"入力を待機",
    r"入力してください",
    r"waiting for input",
    r"waiting for response",
    r"awaiting input",
    r"please enter",
    r"please input",
    r"please provide",
]


@dataclass
class DetectionResult:
    """質問検知結果"""
    detected: bool = False
    question_text: str = ""
    question_type: str = "GENERAL"
    confidence: float = 0.0
    matched_patterns: List[str] = field(default_factory=list)
    options: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessResult:
    """質問処理結果"""
    success: bool = False
    detected: bool = False
    interaction_id: Optional[str] = None
    task_status_updated: bool = False
    message: str = ""
    error: Optional[str] = None
    detection_result: Optional[DetectionResult] = None


class QuestionDetector:
    """
    AI出力から質問を検知するクラス

    Usage:
        detector = QuestionDetector(project_id, task_id)
        result = detector.analyze_and_process(claude_output)
    """

    def __init__(
        self,
        project_id: str,
        task_id: str,
        *,
        session_id: Optional[str] = None,
        confidence_threshold: float = 0.5,
        db_path: Optional[Path] = None,
    ):
        self.project_id = project_id
        self.task_id = task_id
        self.session_id = session_id
        self.confidence_threshold = confidence_threshold
        self.db_path = db_path

        # コンパイル済みパターン
        self._question_patterns = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in QUESTION_PATTERNS]
        self._ask_user_patterns = [re.compile(p, re.IGNORECASE) for p in ASK_USER_PATTERNS]
        self._confirmation_patterns = [re.compile(p, re.IGNORECASE) for p in CONFIRMATION_PATTERNS]
        self._input_wait_patterns = [re.compile(p, re.IGNORECASE) for p in INPUT_WAIT_PATTERNS]

    def analyze_output(self, output: str) -> DetectionResult:
        """
        出力テキストを分析して質問を検知

        Args:
            output: claude -p の出力テキスト

        Returns:
            DetectionResult: 検知結果
        """
        result = DetectionResult()

        if not output or not output.strip():
            return result

        # 行ごとに分析
        lines = output.strip().split('\n')
        last_lines = lines[-10:] if len(lines) > 10 else lines  # 最後の10行を重視

        # 各パターンをチェック
        scores = []

        # 1. AskUserQuestion パターン（最も確実）
        for pattern in self._ask_user_patterns:
            for line in lines:
                if pattern.search(line):
                    scores.append(1.0)
                    result.matched_patterns.append(f"ask_user: {pattern.pattern}")
                    result.question_type = "CHOICE"
                    # AskUserQuestion形式から質問と選択肢を抽出
                    extracted = self._extract_ask_user_question(output)
                    if extracted:
                        result.question_text = extracted[0]
                        result.options = extracted[1]

        # 2. 確認待ちパターン
        for pattern in self._confirmation_patterns:
            for line in last_lines:
                if pattern.search(line):
                    scores.append(0.9)
                    result.matched_patterns.append(f"confirmation: {pattern.pattern}")
                    result.question_type = "CONFIRMATION"
                    if not result.question_text:
                        result.question_text = line.strip()

        # 3. 入力待ちパターン
        for pattern in self._input_wait_patterns:
            for line in last_lines:
                if pattern.search(line):
                    scores.append(0.85)
                    result.matched_patterns.append(f"input_wait: {pattern.pattern}")
                    result.question_type = "INPUT"
                    if not result.question_text:
                        result.question_text = line.strip()

        # 4. 一般的な質問パターン
        for pattern in self._question_patterns:
            for line in last_lines:
                if pattern.search(line):
                    scores.append(0.7)
                    result.matched_patterns.append(f"question: {pattern.pattern}")
                    if not result.question_text:
                        result.question_text = line.strip()

        # 信頼度計算
        if scores:
            result.confidence = max(scores)
            result.detected = result.confidence >= self.confidence_threshold

        # 質問テキストが未設定の場合、最後の行を使用
        if result.detected and not result.question_text:
            result.question_text = last_lines[-1].strip() if last_lines else ""

        # コンテキスト情報を保存
        result.context = {
            "total_lines": len(lines),
            "analyzed_lines": len(last_lines),
            "pattern_matches": len(result.matched_patterns),
        }

        return result

    def _extract_ask_user_question(self, output: str) -> Optional[Tuple[str, List[str]]]:
        """
        AskUserQuestion形式から質問と選択肢を抽出

        Args:
            output: 出力テキスト

        Returns:
            (質問文, 選択肢リスト) または None
        """
        try:
            # JSON形式の質問を探す
            json_match = re.search(r'\{[^{}]*"questions"\s*:\s*\[[^\]]+\][^{}]*\}', output, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                questions = data.get("questions", [])
                if questions:
                    q = questions[0]
                    question_text = q.get("question", "")
                    options = [opt.get("label", "") for opt in q.get("options", [])]
                    return (question_text, options)

            # より簡易的なパターンマッチング
            question_match = re.search(r'"question"\s*:\s*"([^"]+)"', output)
            if question_match:
                question_text = question_match.group(1)
                options = []
                # オプションを抽出
                options_match = re.search(r'"options"\s*:\s*\[([^\]]+)\]', output)
                if options_match:
                    labels = re.findall(r'"label"\s*:\s*"([^"]+)"', options_match.group(1))
                    options = labels
                return (question_text, options)

        except (json.JSONDecodeError, AttributeError):
            pass

        return None

    def analyze_and_process(
        self,
        output: str,
        *,
        auto_create_interaction: bool = True,
        auto_update_task: bool = True,
    ) -> ProcessResult:
        """
        出力を分析し、質問検知時はInteraction作成とタスク状態更新を行う

        Args:
            output: claude -p の出力テキスト
            auto_create_interaction: 質問検知時にInteractionを自動作成
            auto_update_task: 質問検知時にタスク状態をWAITING_INPUTに更新

        Returns:
            ProcessResult: 処理結果
        """
        result = ProcessResult()

        try:
            # 1. 質問検知
            detection = self.analyze_output(output)
            result.detection_result = detection
            result.detected = detection.detected

            if not detection.detected:
                result.success = True
                result.message = "質問は検知されませんでした"
                return result

            # 2. Interaction作成
            if auto_create_interaction:
                interaction_result = self._create_interaction(detection)
                if not interaction_result["success"]:
                    result.error = interaction_result.get("error")
                    return result
                result.interaction_id = interaction_result.get("interaction_id")

            # 3. タスク状態更新
            if auto_update_task:
                update_result = self._update_task_status()
                result.task_status_updated = update_result

            result.success = True
            result.message = f"質問を検知しました: {detection.question_text[:50]}..."

        except Exception as e:
            result.error = f"処理エラー: {e}"

        return result

    def _create_interaction(self, detection: DetectionResult) -> Dict[str, Any]:
        """Interactionを作成"""
        try:
            from interaction.create import create_interaction

            result = create_interaction(
                project_id=self.project_id,
                task_id=self.task_id,
                question_text=detection.question_text,
                session_id=self.session_id,
                question_type=detection.question_type,
                options=detection.options if detection.options else None,
                context={
                    "confidence": detection.confidence,
                    "matched_patterns": detection.matched_patterns,
                    **detection.context,
                },
                db_path=self.db_path,
            )

            return {
                "success": result.success,
                "interaction_id": result.interaction_id,
                "error": result.error,
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _update_task_status(self) -> bool:
        """タスク状態をWAITING_INPUTに更新"""
        try:
            with transaction(db_path=self.db_path) as conn:
                # 現在の状態を確認
                task = fetch_one(
                    conn,
                    "SELECT status FROM tasks WHERE id = ? AND project_id = ?",
                    (self.task_id, self.project_id)
                )

                if not task:
                    return False

                current_status = task["status"]

                # IN_PROGRESS の場合のみ更新
                if current_status != "IN_PROGRESS":
                    return False

                # WAITING_INPUT に更新
                execute_query(
                    conn,
                    """
                    UPDATE tasks
                    SET status = 'WAITING_INPUT', updated_at = ?
                    WHERE id = ? AND project_id = ?
                    """,
                    (datetime.now().isoformat(), self.task_id, self.project_id)
                )

                # 変更履歴を記録
                record_transition(
                    conn,
                    "task",
                    self.task_id,
                    current_status,
                    "WAITING_INPUT",
                    "System",
                    "AI質問検知による状態変更",
                    project_id=self.project_id,
                )

                return True

        except Exception as e:
            print(f"タスク状態更新エラー: {e}", file=sys.stderr)
            return False


def main():
    """コマンドライン実行"""
    # Windows環境でのUTF-8出力設定
    try:
        from config import setup_utf8_output
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from config import setup_utf8_output
    setup_utf8_output()

    parser = argparse.ArgumentParser(
        description="AI質問検知（手動テスト用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # テキストを直接指定
  python detect.py AI_PM_PJ TASK_123 --text "続行しますか？"

  # ファイルから読み込み
  python detect.py AI_PM_PJ TASK_123 --file output.txt

  # 分析のみ（Interaction作成・タスク更新なし）
  python detect.py AI_PM_PJ TASK_123 --text "質問？" --analyze-only
"""
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("task_id", help="タスクID")
    parser.add_argument("--text", "-t", help="分析対象テキスト")
    parser.add_argument("--file", "-f", help="分析対象ファイル")
    parser.add_argument("--analyze-only", action="store_true", help="分析のみ（Interaction作成・タスク更新なし）")
    parser.add_argument("--threshold", type=float, default=0.5, help="検知閾値（0.0-1.0）")
    parser.add_argument("--json", action="store_true", help="JSON形式で出力")

    args = parser.parse_args()

    # テキスト取得
    text = ""
    if args.text:
        text = args.text
    elif args.file:
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                text = f.read()
        except Exception as e:
            print(f"[ERROR] ファイル読み込みエラー: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        print("[ERROR] --text または --file を指定してください", file=sys.stderr)
        sys.exit(1)

    # 検知実行
    detector = QuestionDetector(
        args.project_id,
        args.task_id,
        confidence_threshold=args.threshold,
    )

    if args.analyze_only:
        result = detector.analyze_output(text)
        if args.json:
            output = {
                "detected": result.detected,
                "question_text": result.question_text,
                "question_type": result.question_type,
                "confidence": result.confidence,
                "matched_patterns": result.matched_patterns,
                "options": result.options,
                "context": result.context,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(f"検知結果: {'質問あり' if result.detected else '質問なし'}")
            print(f"信頼度: {result.confidence:.2f}")
            print(f"質問タイプ: {result.question_type}")
            if result.question_text:
                print(f"質問文: {result.question_text}")
            if result.options:
                print(f"選択肢: {result.options}")
            if result.matched_patterns:
                print(f"マッチパターン: {result.matched_patterns}")
    else:
        result = detector.analyze_and_process(text)
        if args.json:
            output = {
                "success": result.success,
                "detected": result.detected,
                "interaction_id": result.interaction_id,
                "task_status_updated": result.task_status_updated,
                "message": result.message,
                "error": result.error,
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            if result.success:
                print(f"[OK] {result.message}")
                if result.interaction_id:
                    print(f"  Interaction ID: {result.interaction_id}")
                if result.task_status_updated:
                    print(f"  タスク状態: WAITING_INPUT に更新")
            else:
                print(f"[ERROR] {result.error}", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
