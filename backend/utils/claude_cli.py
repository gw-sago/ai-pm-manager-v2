"""
claude_cli - Claude CLI (claude -p) ラッパーモジュール

claude_runner モジュールの代替実装。
subprocess.run(['claude', '-p', ...]) でClaude CLIを呼び出し、
既存コードと互換性のあるインターフェースを提供する。

D案アーキテクチャ（ORDER_168）:
  Step 1: Python直接処理（バリデーション、コンテキスト準備）
  Step 2: subprocess で claude -p を呼び出し（AI処理）
  Step 3: Python直接処理（結果パース、DB登録）
"""

import logging
import os
import subprocess
import shutil
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ClaudeResult:
    """Claude CLI実行結果（claude_runner.ClaudeResult互換）"""
    success: bool
    result_text: str = ""
    error_message: Optional[str] = None
    cost_usd: Optional[float] = None


class ClaudeRunner:
    """Claude CLI実行ラッパー（claude_runner.ClaudeRunner互換）"""

    def __init__(
        self,
        model: str = "sonnet",
        max_turns: int = 1,
        timeout_seconds: int = 600,
        stream_output: bool = False,
    ):
        self.model = model
        self.max_turns = max_turns
        self.timeout_seconds = timeout_seconds
        self.stream_output = stream_output

        # claude CLIの存在確認
        self._claude_path = shutil.which("claude")
        if not self._claude_path:
            raise RuntimeError(
                "claude CLI が見つかりません。"
                "Claude Code をインストールしてください: https://docs.anthropic.com/en/docs/claude-code"
            )

    def run(self, prompt: str) -> ClaudeResult:
        """
        Claude CLIでプロンプトを実行

        Args:
            prompt: 実行するプロンプト

        Returns:
            ClaudeResult: 実行結果
        """
        # プロンプトはstdin経由で渡す（Windows cmd.exe経由での日本語文字化け防止）
        cmd = [
            self._claude_path,
            "-p",
            "--dangerously-skip-permissions",
        ]

        # モデル指定（claude CLIの --model オプション）
        if self.model:
            cmd.append(f"--model={self.model}")

        # max_turns指定
        if self.max_turns and self.max_turns > 0:
            cmd.append(f"--max-turns={self.max_turns}")

        logger.info(f"[claude_cli] Executing: claude -p (model={self.model}, timeout={self.timeout_seconds}s)")

        try:
            # CLAUDECODE環境変数を除去してネストセッションエラーを防止
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                encoding="utf-8",
                errors="replace",
                env=env,
            )

            if result.returncode == 0:
                return ClaudeResult(
                    success=True,
                    result_text=result.stdout.strip(),
                    error_message=None,
                    cost_usd=None,  # CLIからはコスト情報取得不可
                )
            else:
                error_msg = result.stderr.strip() or f"claude -p exited with code {result.returncode}"
                logger.error(f"[claude_cli] Error: {error_msg}")
                return ClaudeResult(
                    success=False,
                    result_text=result.stdout.strip(),
                    error_message=error_msg,
                    cost_usd=None,
                )

        except subprocess.TimeoutExpired:
            error_msg = f"claude -p がタイムアウトしました ({self.timeout_seconds}秒)"
            logger.error(f"[claude_cli] {error_msg}")
            return ClaudeResult(
                success=False,
                result_text="",
                error_message=error_msg,
                cost_usd=None,
            )
        except FileNotFoundError:
            error_msg = "claude コマンドが見つかりません"
            logger.error(f"[claude_cli] {error_msg}")
            return ClaudeResult(
                success=False,
                result_text="",
                error_message=error_msg,
                cost_usd=None,
            )
        except Exception as e:
            error_msg = f"claude -p 実行中に予期しないエラー: {e}"
            logger.error(f"[claude_cli] {error_msg}")
            return ClaudeResult(
                success=False,
                result_text="",
                error_message=error_msg,
                cost_usd=None,
            )


def create_runner(
    model: str = "sonnet",
    max_turns: int = 1,
    timeout_seconds: int = 600,
    stream_output: bool = False,
) -> ClaudeRunner:
    """
    ClaudeRunnerインスタンスを生成（claude_runner.create_runner互換）

    Args:
        model: 使用モデル（"opus", "sonnet", "haiku"）
        max_turns: 最大ターン数
        timeout_seconds: タイムアウト秒数
        stream_output: ストリーム出力（現在は未使用、互換性のため残存）

    Returns:
        ClaudeRunner: 実行ラッパーインスタンス
    """
    return ClaudeRunner(
        model=model,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds,
        stream_output=stream_output,
    )
