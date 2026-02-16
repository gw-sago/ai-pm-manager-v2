#!/usr/bin/env python3
"""
AI PM Framework - Worker成果物 自動検証モジュール

Worker実行完了後の成果物に対して lint / test / typecheck を自動実行し、
結果を構造化データ（VerificationResult）で返す。

検証ツールが存在しない場合はスキップし、エラーにはならない。

Usage:
    from worker.self_verification import SelfVerificationRunner

    runner = SelfVerificationRunner(
        project_dir=Path("/path/to/project"),
        artifacts=["src/main.py", "src/utils.py"],
        timeout=120,
    )
    result = runner.run_verification()

    if not result.success:
        fix_prompt = runner.build_fix_prompt(result, task_spec="...")
"""

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

logger = logging.getLogger(__name__)

# Windows判定
_IS_WINDOWS = sys.platform == "win32"


@dataclass
class VerificationCheck:
    """個別検証チェック結果"""
    type: str           # "lint" / "test" / "typecheck"
    command: str        # 実行したコマンド
    passed: bool        # 成功/失敗
    output: str         # コマンド出力
    errors: List[str]   # パース済みエラー一覧

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "type": self.type,
            "command": self.command,
            "passed": self.passed,
            "output": self.output,
            "errors": self.errors,
        }


@dataclass
class VerificationResult:
    """検証結果全体"""
    success: bool                           # 全チェック通過
    checks: List[VerificationCheck]         # VerificationCheck のリスト
    skipped_checks: List[str]               # ツール未検出でスキップしたチェック名
    duration_seconds: float                 # 実行時間（秒）

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "success": self.success,
            "checks": [c.to_dict() for c in self.checks],
            "skipped_checks": self.skipped_checks,
            "duration_seconds": round(self.duration_seconds, 2),
        }

    def summary_text(self) -> str:
        """検証結果の要約テキストを生成"""
        lines = []
        total = len(self.checks) + len(self.skipped_checks)
        passed = sum(1 for c in self.checks if c.passed)
        failed = sum(1 for c in self.checks if not c.passed)
        skipped = len(self.skipped_checks)

        lines.append(f"Verification: {passed} passed, {failed} failed, {skipped} skipped (total {total})")
        lines.append(f"Duration: {self.duration_seconds:.1f}s")

        for check in self.checks:
            status = "PASS" if check.passed else "FAIL"
            lines.append(f"  [{status}] {check.type}: {check.command}")
            if not check.passed and check.errors:
                for err in check.errors[:5]:
                    lines.append(f"         {err}")
                if len(check.errors) > 5:
                    lines.append(f"         ... and {len(check.errors) - 5} more errors")

        if self.skipped_checks:
            lines.append(f"  [SKIP] {', '.join(self.skipped_checks)}")

        return "\n".join(lines)


@dataclass
class DetectedTools:
    """検出された検証ツール情報"""
    lint: Optional[str] = None          # lint コマンド
    test: Optional[str] = None          # test コマンド
    typecheck: Optional[str] = None     # typecheck コマンド
    project_type: str = "unknown"       # "python" / "node" / "unknown"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lint": self.lint,
            "test": self.test,
            "typecheck": self.typecheck,
            "project_type": self.project_type,
        }


class SelfVerificationRunner:
    """
    Worker成果物の自動検証

    プロジェクトディレクトリと成果物リストを受け取り、
    検証ツールを自動検出して lint / test / typecheck を実行する。
    """

    def __init__(
        self,
        project_dir: Path,
        artifacts: Optional[List[str]] = None,
        timeout: int = 120,
    ):
        """
        Args:
            project_dir: プロジェクトディレクトリ（検証コマンドの実行ディレクトリ）
            artifacts: 成果物ファイルパスのリスト
            timeout: 各コマンドのタイムアウト秒数（デフォルト: 120秒）
        """
        self.project_dir = Path(project_dir).resolve()
        self.artifacts = artifacts or []
        self.timeout = timeout

        # 成果物からプロジェクトルートを推定
        self._effective_root = self._resolve_project_root()

        logger.debug(
            f"SelfVerificationRunner initialized: "
            f"project_dir={self.project_dir}, "
            f"effective_root={self._effective_root}, "
            f"artifacts={len(self.artifacts)}, "
            f"timeout={self.timeout}s"
        )

    def _resolve_project_root(self) -> Path:
        """
        成果物パスからプロジェクトルートを推定する。

        成果物パスの共通ディレクトリ祖先を使用する。
        成果物が空の場合は project_dir をそのまま使用する。

        Returns:
            推定されたプロジェクトルートのPath
        """
        if not self.artifacts:
            return self.project_dir

        # 成果物の絶対パスリストを作成
        abs_paths = []
        for artifact in self.artifacts:
            p = Path(artifact)
            if not p.is_absolute():
                p = self.project_dir / p
            p = p.resolve()
            # ファイルの場合は親ディレクトリを使用
            if p.is_file() or not p.exists():
                p = p.parent
            abs_paths.append(p)

        if not abs_paths:
            return self.project_dir

        # 共通祖先を算出
        try:
            common = abs_paths[0]
            for p in abs_paths[1:]:
                # パーツの共通部分を取得
                common_parts = []
                for a, b in zip(common.parts, p.parts):
                    if a == b:
                        common_parts.append(a)
                    else:
                        break
                if common_parts:
                    common = Path(*common_parts) if len(common_parts) > 1 else Path(common_parts[0])
                else:
                    # 共通部分がない場合は project_dir にフォールバック
                    return self.project_dir

            # 共通祖先がプロジェクトディレクトリより上位の場合は project_dir を使用
            try:
                common.relative_to(self.project_dir)
                return common
            except ValueError:
                return self.project_dir

        except Exception as e:
            logger.debug(f"プロジェクトルート推定に失敗: {e}")
            return self.project_dir

    def detect_tools(self) -> DetectedTools:
        """
        プロジェクトの検証ツールを自動検出する。

        検出ロジック:
        1. Python プロジェクト: pyproject.toml / setup.cfg / requirements.txt
           - lint: ruff check . (ruff --version 成功時)
           - test: pytest (pytest --co -q 成功時)
           - typecheck: mypy . (mypy --version 成功時)
        2. Node.js プロジェクト: package.json
           - scripts セクションから lint / test / typecheck を検出
           - npm run lint / npm test / npm run typecheck

        Returns:
            DetectedTools: 検出された検証ツール情報
        """
        tools = DetectedTools()

        # Python プロジェクト検出
        python_markers = [
            self._effective_root / "pyproject.toml",
            self._effective_root / "setup.cfg",
            self._effective_root / "requirements.txt",
        ]

        is_python = any(marker.exists() for marker in python_markers)

        if is_python:
            tools.project_type = "python"
            logger.debug("Python プロジェクトを検出")

            # ruff 検出
            if self._command_available("ruff", ["ruff", "--version"]):
                tools.lint = "ruff check ."
                logger.debug("ruff を検出: lint 利用可能")

            # pytest 検出
            if self._command_available("pytest", ["pytest", "--co", "-q"]):
                tools.test = "pytest"
                logger.debug("pytest を検出: test 利用可能")

            # mypy 検出
            if self._command_available("mypy", ["mypy", "--version"]):
                tools.typecheck = "mypy ."
                logger.debug("mypy を検出: typecheck 利用可能")

        # Node.js プロジェクト検出
        package_json_path = self._effective_root / "package.json"
        if package_json_path.exists():
            if tools.project_type == "unknown":
                tools.project_type = "node"
            logger.debug("Node.js プロジェクトを検出 (package.json)")

            try:
                package_data = json.loads(
                    package_json_path.read_text(encoding="utf-8")
                )
                scripts = package_data.get("scripts", {})

                # lint スクリプト検出
                if "lint" in scripts and tools.lint is None:
                    tools.lint = "npm run lint"
                    logger.debug("npm run lint を検出")

                # test スクリプト検出
                if "test" in scripts and tools.test is None:
                    tools.test = "npm test"
                    logger.debug("npm test を検出")

                # typecheck スクリプト検出
                typecheck_keys = ["typecheck", "type-check", "tsc"]
                for key in typecheck_keys:
                    if key in scripts and tools.typecheck is None:
                        tools.typecheck = f"npm run {key}"
                        logger.debug(f"npm run {key} を検出")
                        break

            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"package.json の読み込みに失敗: {e}")

        logger.info(
            f"検証ツール検出結果: project_type={tools.project_type}, "
            f"lint={'available' if tools.lint else 'none'}, "
            f"test={'available' if tools.test else 'none'}, "
            f"typecheck={'available' if tools.typecheck else 'none'}"
        )

        return tools

    def _command_available(self, name: str, check_cmd: List[str]) -> bool:
        """
        コマンドが利用可能かどうかを確認する。

        Args:
            name: ツール名（ログ用）
            check_cmd: 確認用コマンド（例: ["ruff", "--version"]）

        Returns:
            コマンドが利用可能ならTrue
        """
        try:
            result = subprocess.run(
                check_cmd,
                capture_output=True,
                timeout=10,
                cwd=str(self._effective_root),
                shell=_IS_WINDOWS,
                encoding="utf-8",
                errors="replace",
            )
            return result.returncode == 0
        except FileNotFoundError:
            logger.debug(f"{name} が見つかりません (FileNotFoundError)")
            return False
        except subprocess.TimeoutExpired:
            logger.debug(f"{name} のバージョン確認がタイムアウト")
            return False
        except OSError as e:
            logger.debug(f"{name} の確認中にOSエラー: {e}")
            return False
        except Exception as e:
            logger.debug(f"{name} の確認中にエラー: {e}")
            return False

    def run_verification(self) -> VerificationResult:
        """
        全検証を実行する。

        検証ツールを自動検出し、利用可能なツールで lint / test / typecheck を実行。
        ツールが未検出の場合はスキップする。

        Returns:
            VerificationResult: 検証結果
        """
        start_time = time.time()
        checks: List[VerificationCheck] = []
        skipped: List[str] = []

        # ツール検出
        tools = self.detect_tools()

        # lint 実行
        if tools.lint:
            check = self._run_check("lint", tools.lint)
            checks.append(check)
        else:
            skipped.append("lint")
            logger.info("lint: ツール未検出のためスキップ")

        # test 実行
        if tools.test:
            check = self._run_check("test", tools.test)
            checks.append(check)
        else:
            skipped.append("test")
            logger.info("test: ツール未検出のためスキップ")

        # typecheck 実行
        if tools.typecheck:
            check = self._run_check("typecheck", tools.typecheck)
            checks.append(check)
        else:
            skipped.append("typecheck")
            logger.info("typecheck: ツール未検出のためスキップ")

        duration = time.time() - start_time

        # 全チェック通過判定（チェックが0件の場合もsuccessとする）
        all_passed = all(c.passed for c in checks) if checks else True

        result = VerificationResult(
            success=all_passed,
            checks=checks,
            skipped_checks=skipped,
            duration_seconds=duration,
        )

        logger.info(f"検証完了: {result.summary_text()}")
        return result

    def _run_check(self, check_type: str, command: str) -> VerificationCheck:
        """
        個別検証チェックを実行する。

        Args:
            check_type: チェック種別 ("lint" / "test" / "typecheck")
            command: 実行するコマンド文字列

        Returns:
            VerificationCheck: チェック結果
        """
        logger.info(f"検証実行中: [{check_type}] {command}")

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                timeout=self.timeout,
                cwd=str(self._effective_root),
                shell=True,
                encoding="utf-8",
                errors="replace",
            )

            output = result.stdout + result.stderr
            passed = result.returncode == 0
            errors = self._parse_errors(check_type, output, result.returncode)

            logger.info(
                f"検証結果: [{check_type}] "
                f"{'PASS' if passed else 'FAIL'} "
                f"(exit_code={result.returncode}, errors={len(errors)})"
            )

            return VerificationCheck(
                type=check_type,
                command=command,
                passed=passed,
                output=self._truncate_output(output),
                errors=errors,
            )

        except subprocess.TimeoutExpired:
            error_msg = f"タイムアウト ({self.timeout}秒)"
            logger.warning(f"検証タイムアウト: [{check_type}] {command}")
            return VerificationCheck(
                type=check_type,
                command=command,
                passed=False,
                output=error_msg,
                errors=[error_msg],
            )

        except FileNotFoundError as e:
            error_msg = f"コマンドが見つかりません: {e}"
            logger.warning(f"検証エラー: [{check_type}] {error_msg}")
            return VerificationCheck(
                type=check_type,
                command=command,
                passed=False,
                output=error_msg,
                errors=[error_msg],
            )

        except OSError as e:
            error_msg = f"OSエラー: {e}"
            logger.warning(f"検証エラー: [{check_type}] {error_msg}")
            return VerificationCheck(
                type=check_type,
                command=command,
                passed=False,
                output=error_msg,
                errors=[error_msg],
            )

        except Exception as e:
            error_msg = f"予期しないエラー: {e}"
            logger.warning(f"検証エラー: [{check_type}] {error_msg}")
            return VerificationCheck(
                type=check_type,
                command=command,
                passed=False,
                output=error_msg,
                errors=[error_msg],
            )

    def _parse_errors(
        self, check_type: str, output: str, return_code: int
    ) -> List[str]:
        """
        検証コマンドの出力からエラー行を抽出する。

        Args:
            check_type: チェック種別
            output: コマンド出力
            return_code: 終了コード

        Returns:
            パース済みエラー行のリスト
        """
        if return_code == 0:
            return []

        errors = []

        if check_type == "lint":
            # ruff / eslint 形式: ファイルパス:行:列: メッセージ
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                # ruff形式: path.py:10:5: E501 ...
                if ":" in line and any(
                    marker in line
                    for marker in ["error", "warning", "Error", "Warning", "E", "W", "F"]
                ):
                    errors.append(line)

        elif check_type == "test":
            # pytest 形式: FAILED / ERROR 行を抽出
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.startswith("FAILED") or line.startswith("ERROR"):
                    errors.append(line)
                elif "FAILURES" in line or "ERRORS" in line:
                    errors.append(line)
                # pytest short test summary 以降の行
                elif line.startswith("E ") or line.startswith("> "):
                    errors.append(line)

        elif check_type == "typecheck":
            # mypy / tsc 形式: ファイルパス:行: error: メッセージ
            for line in output.splitlines():
                line = line.strip()
                if not line:
                    continue
                if "error" in line.lower() and ":" in line:
                    errors.append(line)

        # エラーが見つからなかった場合、出力の最後の数行を返す
        if not errors and return_code != 0:
            output_lines = [
                l.strip() for l in output.splitlines() if l.strip()
            ]
            errors = output_lines[-10:] if output_lines else [
                f"exit_code={return_code} (no parseable errors)"
            ]

        return errors

    def _truncate_output(self, output: str, max_chars: int = 10000) -> str:
        """
        出力文字列を最大長に切り詰める。

        Args:
            output: 元の出力
            max_chars: 最大文字数

        Returns:
            切り詰めた出力文字列
        """
        if len(output) <= max_chars:
            return output
        half = max_chars // 2
        return (
            output[:half]
            + f"\n\n... (truncated {len(output) - max_chars} chars) ...\n\n"
            + output[-half:]
        )

    def build_fix_prompt(
        self, result: VerificationResult, task_spec: str = ""
    ) -> str:
        """
        自己修正用プロンプトを生成する。

        検証で失敗したチェックの情報を元に、Worker が修正を行うための
        プロンプトを組み立てる。

        Args:
            result: 検証結果
            task_spec: 元のタスク仕様（コンテキスト用）

        Returns:
            自己修正用プロンプト文字列
        """
        if result.success:
            return ""

        failed_checks = [c for c in result.checks if not c.passed]

        if not failed_checks:
            return ""

        sections = []

        sections.append("# 自己修正指示")
        sections.append("")
        sections.append(
            "以下の検証チェックが失敗しました。エラーを修正してください。"
        )
        sections.append("")

        for check in failed_checks:
            sections.append(f"## {check.type} 検証失敗")
            sections.append(f"- コマンド: `{check.command}`")
            sections.append("")

            if check.errors:
                sections.append("### エラー一覧")
                sections.append("```")
                for err in check.errors:
                    sections.append(err)
                sections.append("```")
                sections.append("")

            if check.output and check.output != check.errors:
                sections.append("### コマンド出力（抜粋）")
                # 出力は長くなる可能性があるので、先頭部分のみ
                truncated = self._truncate_output(check.output, max_chars=3000)
                sections.append("```")
                sections.append(truncated)
                sections.append("```")
                sections.append("")

        # 成果物リスト
        if self.artifacts:
            sections.append("## 対象ファイル")
            for artifact in self.artifacts:
                sections.append(f"- `{artifact}`")
            sections.append("")

        # 元タスク仕様
        if task_spec:
            sections.append("## 元のタスク仕様")
            sections.append(task_spec)
            sections.append("")

        sections.append("## 修正指針")
        sections.append("1. 上記のエラー内容を確認してください")
        sections.append("2. 各エラーの原因を特定し、修正を行ってください")
        sections.append("3. 修正後、検証が通過することを確認してください")
        sections.append(
            "4. 元のタスク仕様の完了条件を満たしていることも確認してください"
        )
        sections.append("")

        return "\n".join(sections)
