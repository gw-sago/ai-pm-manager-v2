#!/usr/bin/env python3
"""
AI PM Framework - Static Analyzer

Worker完了後に成果物ファイルに対して静的解析を自動実行するモジュール。
利用可能なツール（ruff, mypy, tsc, eslint）を自動検出し、
検出されたツールで解析を実行する。

Usage:
    from quality.static_analyzer import StaticAnalyzer

    analyzer = StaticAnalyzer(project_root="/path/to/project")
    result = analyzer.analyze(["src/main.py", "src/utils.py"])
    print(result)

Windows環境対応:
    - コマンド検出は `where` を使用
    - パスのバックスラッシュに対応
"""

import json
import logging
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ツール実行タイムアウト（秒）
TOOL_TIMEOUT_SECONDS = 60


@dataclass
class AnalysisIssue:
    """静的解析で検出された個別の問題を表すデータクラス。

    全フィールドがJSONシリアライズ可能な型のみで構成される。
    """

    file: str
    line: int
    col: int
    tool: str
    severity: str  # "error" or "warning"
    message: str

    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換する。"""
        return asdict(self)


@dataclass
class AnalysisResult:
    """静的解析の実行結果を表すデータクラス。"""

    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    fixed: List[Dict[str, Any]] = field(default_factory=list)
    score: int = 100
    tools_used: List[str] = field(default_factory=list)
    skipped_tools: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換する。"""
        return asdict(self)


class StaticAnalyzer:
    """静的解析エンジン本体。

    プロジェクトルートを基準に利用可能なツールを自動検出し、
    指定されたファイル群に対して静的解析を実行する。

    Attributes:
        project_root: プロジェクトルートディレクトリのパス
        _is_windows: Windows環境かどうか
        _detected_tools: detect_tools() の結果キャッシュ
    """

    def __init__(self, project_root: str) -> None:
        """プロジェクトルートを受け取り、利用可能なツールを自動検出する。

        Args:
            project_root: プロジェクトルートディレクトリの絶対パス
        """
        self.project_root = Path(project_root).resolve()
        self._is_windows = platform.system() == "Windows"
        self._detected_tools: Optional[Dict[str, bool]] = None
        logger.info(
            "StaticAnalyzer initialized: project_root=%s, platform=%s",
            self.project_root,
            platform.system(),
        )

    def detect_tools(self) -> Dict[str, bool]:
        """利用可能な解析ツールを検出する。

        各ツールのコマンド存在確認と、プロジェクト内の設定ファイル存在チェックを行う。

        Returns:
            ツール名をキー、利用可否をbool値とした辞書。
            例: {"ruff": True, "mypy": False, "tsc": True, "eslint": False}
        """
        if self._detected_tools is not None:
            return self._detected_tools

        tools: Dict[str, bool] = {
            "ruff": False,
            "mypy": False,
            "tsc": False,
            "eslint": False,
        }

        # ruff: コマンド存在確認
        tools["ruff"] = self._command_exists("ruff")
        logger.debug("ruff available: %s", tools["ruff"])

        # mypy: コマンド存在確認
        tools["mypy"] = self._command_exists("mypy")
        logger.debug("mypy available: %s", tools["mypy"])

        # tsc: tsconfig.json の存在確認 + コマンド確認
        tsconfig_exists = (self.project_root / "tsconfig.json").exists()
        if tsconfig_exists:
            tsc_available = self._command_exists("tsc") or self._npx_available("tsc")
            tools["tsc"] = tsc_available
        else:
            tools["tsc"] = False
        logger.debug(
            "tsc available: %s (tsconfig=%s)", tools["tsc"], tsconfig_exists
        )

        # eslint: 設定ファイルの存在確認
        eslint_config_exists = self._has_eslint_config()
        if eslint_config_exists:
            tools["eslint"] = self._command_exists("eslint") or self._npx_available(
                "eslint"
            )
        else:
            tools["eslint"] = False
        logger.debug(
            "eslint available: %s (config=%s)", tools["eslint"], eslint_config_exists
        )

        self._detected_tools = tools
        logger.info("Detected tools: %s", tools)
        return tools

    def analyze(self, files: Optional[List[str]] = None) -> Dict[str, Any]:
        """指定ファイルに対して静的解析を実行する。

        Args:
            files: 解析対象ファイルパスのリスト。Noneの場合は空リストとして扱う。
                   BUG_001対策: ミュータブルデフォルト引数を使わない。

        Returns:
            解析結果の辞書。以下のキーを含む:
            - errors: エラーのリスト
            - warnings: 警告のリスト
            - fixed: 自動修正されたファイルのリスト
            - score: 品質スコア (0-100)
            - tools_used: 実行されたツールのリスト
            - skipped_tools: スキップされたツールのリスト
        """
        if files is None:
            files = []

        result = AnalysisResult()

        # 対象ファイルなし: スキップ（score=100）
        if not files:
            logger.info("No files to analyze. Returning score=100.")
            return result.to_dict()

        # ファイルをPythonファイルとそれ以外に分類
        py_files = [f for f in files if f.endswith(".py")]
        ts_files = [
            f
            for f in files
            if f.endswith((".ts", ".tsx", ".js", ".jsx"))
        ]

        # ツール検出
        tools = self.detect_tools()

        # ruff: Pythonファイルが対象にある場合のみ
        if tools["ruff"] and py_files:
            try:
                issues = self._run_ruff_check(py_files)
                self._categorize_issues(issues, result)
                result.tools_used.append("ruff")
                logger.info("ruff: %d issues found", len(issues))
            except Exception as e:
                logger.warning("ruff execution failed, skipping: %s", e)
                result.skipped_tools.append("ruff")
        elif not tools["ruff"] and py_files:
            result.skipped_tools.append("ruff")
        # py_files が空なら ruff はスキップ対象にすら入れない

        # mypy: Pythonファイルが対象にある場合のみ
        if tools["mypy"] and py_files:
            try:
                issues = self._run_mypy(py_files)
                self._categorize_issues(issues, result)
                result.tools_used.append("mypy")
                logger.info("mypy: %d issues found", len(issues))
            except Exception as e:
                logger.warning("mypy execution failed, skipping: %s", e)
                result.skipped_tools.append("mypy")
        elif not tools["mypy"] and py_files:
            result.skipped_tools.append("mypy")

        # tsc: TypeScript/JSファイルが対象にある場合のみ
        if tools["tsc"] and ts_files:
            try:
                issues = self._run_tsc(ts_files)
                self._categorize_issues(issues, result)
                result.tools_used.append("tsc")
                logger.info("tsc: %d issues found", len(issues))
            except Exception as e:
                logger.warning("tsc execution failed, skipping: %s", e)
                result.skipped_tools.append("tsc")
        elif not tools["tsc"] and ts_files:
            result.skipped_tools.append("tsc")

        # eslint: TypeScript/JSファイルが対象にある場合のみ
        if tools["eslint"] and ts_files:
            try:
                issues = self._run_eslint(ts_files)
                self._categorize_issues(issues, result)
                result.tools_used.append("eslint")
                logger.info("eslint: %d issues found", len(issues))
            except Exception as e:
                logger.warning("eslint execution failed, skipping: %s", e)
                result.skipped_tools.append("eslint")
        elif not tools["eslint"] and ts_files:
            result.skipped_tools.append("eslint")

        # スコア計算
        result.score = self._calculate_score(
            len(result.errors), len(result.warnings)
        )

        logger.info(
            "Analysis complete: score=%d, errors=%d, warnings=%d, tools_used=%s, skipped=%s",
            result.score,
            len(result.errors),
            len(result.warnings),
            result.tools_used,
            result.skipped_tools,
        )

        return result.to_dict()

    # ------------------------------------------------------------------
    # Private: ツール実行メソッド
    # ------------------------------------------------------------------

    def _run_ruff_check(self, files: List[str]) -> List[AnalysisIssue]:
        """ruff check を実行し、検出された問題を返す。

        Args:
            files: 解析対象のPythonファイルパスリスト

        Returns:
            AnalysisIssue のリスト

        Raises:
            RuntimeError: ツール実行が想定外の失敗をした場合
        """
        # ruff check --output-format json で構造化出力を取得
        cmd = ["ruff", "check", "--output-format", "json"] + files
        logger.debug("Running ruff: %s", " ".join(cmd))

        proc = self._run_subprocess(cmd)

        # ruff は問題検出時に exit code 1 を返す（正常動作）
        if proc.returncode not in (0, 1):
            raise RuntimeError(
                f"ruff check failed with exit code {proc.returncode}: "
                f"{proc.stderr}"
            )

        issues: List[AnalysisIssue] = []

        if not proc.stdout.strip():
            return issues

        try:
            ruff_results = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse ruff JSON output: %s", e)
            return issues

        for entry in ruff_results:
            # ruff JSON format: {"code": "F401", "message": "...",
            #   "location": {"row": 1, "column": 1}, "filename": "...", ...}
            severity = self._ruff_severity(entry.get("code", ""))
            issue = AnalysisIssue(
                file=entry.get("filename", ""),
                line=entry.get("location", {}).get("row", 0),
                col=entry.get("location", {}).get("column", 0),
                tool="ruff",
                severity=severity,
                message=f"[{entry.get('code', '')}] {entry.get('message', '')}",
            )
            issues.append(issue)

        return issues

    def _run_mypy(self, files: List[str]) -> List[AnalysisIssue]:
        """mypy を実行し、検出された問題を返す。

        Args:
            files: 解析対象のPythonファイルパスリスト

        Returns:
            AnalysisIssue のリスト

        Raises:
            RuntimeError: ツール実行が想定外の失敗をした場合
        """
        # mypy --no-color-output --show-column-numbers --no-error-summary
        cmd = [
            "mypy",
            "--no-color-output",
            "--show-column-numbers",
            "--no-error-summary",
            "--ignore-missing-imports",
        ] + files
        logger.debug("Running mypy: %s", " ".join(cmd))

        proc = self._run_subprocess(cmd)

        # mypy は問題検出時に exit code 1 を返す（正常動作）
        if proc.returncode not in (0, 1):
            raise RuntimeError(
                f"mypy failed with exit code {proc.returncode}: {proc.stderr}"
            )

        issues: List[AnalysisIssue] = []

        if not proc.stdout.strip():
            return issues

        # mypy 出力形式: file.py:line:col: severity: message
        # 例: src/main.py:10:5: error: Incompatible types in assignment
        pattern = re.compile(
            r"^(.+?):(\d+):(\d+):\s*(error|warning|note):\s*(.+)$"
        )

        for line in proc.stdout.splitlines():
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue

            filepath, line_no, col_no, severity_str, message = match.groups()

            # note は無視（情報提供のみ）
            if severity_str == "note":
                continue

            severity = "error" if severity_str == "error" else "warning"
            issue = AnalysisIssue(
                file=filepath,
                line=int(line_no),
                col=int(col_no),
                tool="mypy",
                severity=severity,
                message=message,
            )
            issues.append(issue)

        return issues

    def _run_tsc(self, files: List[str]) -> List[AnalysisIssue]:
        """tsc (TypeScript Compiler) を実行し、検出された問題を返す。

        Args:
            files: 解析対象のTypeScript/JSファイルパスリスト

        Returns:
            AnalysisIssue のリスト

        Raises:
            RuntimeError: ツール実行が想定外の失敗をした場合
        """
        # tsc --noEmit でコンパイルエラーのみチェック
        # npx 経由で実行を試みる
        if self._command_exists("tsc"):
            cmd = ["tsc", "--noEmit", "--pretty", "false"] + files
        else:
            cmd = ["npx", "tsc", "--noEmit", "--pretty", "false"] + files

        logger.debug("Running tsc: %s", " ".join(cmd))

        proc = self._run_subprocess(cmd)

        # tsc はエラー検出時に exit code 1 を返す（正常動作）
        # exit code 2 はコンフィグエラー等
        if proc.returncode not in (0, 1, 2):
            raise RuntimeError(
                f"tsc failed with exit code {proc.returncode}: {proc.stderr}"
            )

        issues: List[AnalysisIssue] = []

        if not proc.stdout.strip():
            return issues

        # tsc 出力形式: file.ts(line,col): error TSxxxx: message
        # 例: src/app.ts(5,10): error TS2322: Type 'string' is not assignable
        pattern = re.compile(
            r"^(.+?)\((\d+),(\d+)\):\s*(error|warning)\s+(TS\d+):\s*(.+)$"
        )

        for line in proc.stdout.splitlines():
            line = line.strip()
            match = pattern.match(line)
            if not match:
                continue

            filepath, line_no, col_no, severity_str, ts_code, message = (
                match.groups()
            )
            severity = "error" if severity_str == "error" else "warning"
            issue = AnalysisIssue(
                file=filepath,
                line=int(line_no),
                col=int(col_no),
                tool="tsc",
                severity=severity,
                message=f"[{ts_code}] {message}",
            )
            issues.append(issue)

        return issues

    def _run_eslint(self, files: List[str]) -> List[AnalysisIssue]:
        """eslint を実行し、検出された問題を返す。

        Args:
            files: 解析対象のJS/TSファイルパスリスト

        Returns:
            AnalysisIssue のリスト

        Raises:
            RuntimeError: ツール実行が想定外の失敗をした場合
        """
        # eslint --format json で構造化出力を取得
        if self._command_exists("eslint"):
            cmd = ["eslint", "--format", "json"] + files
        else:
            cmd = ["npx", "eslint", "--format", "json"] + files

        logger.debug("Running eslint: %s", " ".join(cmd))

        proc = self._run_subprocess(cmd)

        # eslint は問題検出時に exit code 1 を返す（正常動作）
        # exit code 2 は設定エラー等
        if proc.returncode not in (0, 1):
            raise RuntimeError(
                f"eslint failed with exit code {proc.returncode}: "
                f"{proc.stderr}"
            )

        issues: List[AnalysisIssue] = []

        if not proc.stdout.strip():
            return issues

        try:
            eslint_results = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse eslint JSON output: %s", e)
            return issues

        # eslint JSON format:
        # [{"filePath": "...", "messages": [{"ruleId": "...", "severity": 1|2,
        #   "message": "...", "line": 1, "column": 1}]}]
        for file_result in eslint_results:
            filepath = file_result.get("filePath", "")
            for msg in file_result.get("messages", []):
                # eslint severity: 1 = warning, 2 = error
                eslint_severity = msg.get("severity", 1)
                severity = "error" if eslint_severity == 2 else "warning"
                rule_id = msg.get("ruleId", "unknown")
                issue = AnalysisIssue(
                    file=filepath,
                    line=msg.get("line", 0),
                    col=msg.get("column", 0),
                    tool="eslint",
                    severity=severity,
                    message=f"[{rule_id}] {msg.get('message', '')}",
                )
                issues.append(issue)

        return issues

    # ------------------------------------------------------------------
    # Private: ユーティリティ
    # ------------------------------------------------------------------

    def _command_exists(self, command: str) -> bool:
        """コマンドがシステムに存在するか確認する。

        Windows では `where`、Unix系では `which` を使用する。

        Args:
            command: 確認するコマンド名

        Returns:
            コマンドが存在すれば True
        """
        check_cmd = "where" if self._is_windows else "which"
        try:
            proc = subprocess.run(
                [check_cmd, command],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _npx_available(self, package: str) -> bool:
        """npx 経由でパッケージが利用可能か確認する。

        Args:
            package: 確認するnpmパッケージ名

        Returns:
            npx 経由で利用可能なら True
        """
        try:
            proc = subprocess.run(
                ["npx", "--no-install", package, "--version"],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(self.project_root),
            )
            return proc.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    def _has_eslint_config(self) -> bool:
        """プロジェクトルートにeslint設定ファイルが存在するか確認する。

        Returns:
            eslint設定ファイルが存在すれば True
        """
        config_patterns = [
            ".eslintrc",
            ".eslintrc.js",
            ".eslintrc.cjs",
            ".eslintrc.json",
            ".eslintrc.yml",
            ".eslintrc.yaml",
            "eslint.config.js",
            "eslint.config.mjs",
            "eslint.config.cjs",
            "eslint.config.ts",
        ]
        for pattern in config_patterns:
            if (self.project_root / pattern).exists():
                return True
        return False

    def _run_subprocess(self, cmd: List[str]) -> subprocess.CompletedProcess:
        """サブプロセスを実行する。タイムアウト付き。

        Args:
            cmd: 実行するコマンドと引数のリスト

        Returns:
            subprocess.CompletedProcess オブジェクト

        Raises:
            RuntimeError: タイムアウト発生時
        """
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=TOOL_TIMEOUT_SECONDS,
                cwd=str(self.project_root),
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Command timed out after {TOOL_TIMEOUT_SECONDS}s: "
                f"{' '.join(cmd)}"
            )
        except FileNotFoundError as e:
            raise RuntimeError(f"Command not found: {cmd[0]} ({e})")

    def _ruff_severity(self, code: str) -> str:
        """ruff のルールコードから severity を判定する。

        Args:
            code: ruff ルールコード (例: "F401", "E501", "W291")

        Returns:
            "error" or "warning"
        """
        # E: pycodestyle error, F: Pyflakes, W: pycodestyle warning
        # I: isort, D: pydocstyle, N: pep8-naming
        if code.startswith("W") or code.startswith("D") or code.startswith("I"):
            return "warning"
        return "error"

    def _categorize_issues(
        self, issues: List[AnalysisIssue], result: AnalysisResult
    ) -> None:
        """検出された問題をエラーと警告に分類して result に追加する。

        Args:
            issues: 分類対象の AnalysisIssue リスト
            result: 結果を追加する AnalysisResult
        """
        for issue in issues:
            issue_dict = issue.to_dict()
            if issue.severity == "error":
                result.errors.append(issue_dict)
            else:
                result.warnings.append(issue_dict)

    @staticmethod
    def _calculate_score(error_count: int, warning_count: int) -> int:
        """品質スコアを計算する。

        - base_score = 100
        - error 1件あたり -10点
        - warning 1件あたり -2点
        - 最低0点

        Args:
            error_count: エラー件数
            warning_count: 警告件数

        Returns:
            品質スコア (0-100)
        """
        score = 100 - (error_count * 10) - (warning_count * 2)
        return max(0, score)
