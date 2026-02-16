#!/usr/bin/env python3
"""
AI PM Framework - Auto Fixer

静的解析で検出されたフォーマット系の問題を自動修正するモジュール。
ruff format (Python) と eslint --fix (TypeScript/JavaScript) をサポートする。

Usage:
    from quality.auto_fixer import AutoFixer

    fixer = AutoFixer(project_root="/path/to/project")
    result = fixer.fix(["src/main.py", "src/utils.py"])
    print(result)

Windows環境対応:
    - コマンド検出は `where` を使用
    - パスのバックスラッシュに対応

修正フロー:
    1. 対象ファイルの修正前内容を記録
    2. 自動修正ツール実行
    3. 修正後の内容と比較、diffを生成
    4. 修正結果を構造化して返却
    5. 修正失敗時は元ファイルを復元
"""

import difflib
import logging
import platform
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ツール実行タイムアウト（秒）
TOOL_TIMEOUT_SECONDS = 60


class AutoFixer:
    """自動修正エンジン本体。

    フォーマット系の問題を自動修正する。
    修正前の内容を保持し、失敗時には復元を行う。

    Attributes:
        project_root: プロジェクトルートディレクトリのパス
        _is_windows: Windows環境かどうか
    """

    def __init__(self, project_root: str) -> None:
        """プロジェクトルートを受け取る。

        Args:
            project_root: プロジェクトルートディレクトリの絶対パス
        """
        self.project_root = Path(project_root).resolve()
        self._is_windows = platform.system() == "Windows"
        logger.info(
            "AutoFixer initialized: project_root=%s, platform=%s",
            self.project_root,
            platform.system(),
        )

    def fix(self, files: Optional[List[str]] = None) -> Dict[str, Any]:
        """指定ファイルに対して自動修正を実行する。

        Args:
            files: 修正対象ファイルパスのリスト。
                   Noneの場合は空リスト扱い（BUG_001対策）。

        Returns:
            修正結果の辞書。以下のキーを含む:
            - fixed_count: 修正されたファイル数
            - fixed_files: 修正されたファイルパスのリスト
            - fixes: 修正詳細のリスト
                - file: ファイルパス
                - tool: 使用ツール名
                - description: 修正内容の説明
                - diff: unified diff形式の差分
            - failed: 修正失敗したファイルのリスト
        """
        if files is None:
            files = []

        result: Dict[str, Any] = {
            "fixed_count": 0,
            "fixed_files": [],
            "fixes": [],
            "failed": [],
        }

        if not files:
            logger.info("No files to fix. Returning empty result.")
            return result

        # ファイルをPythonファイルとTS/JSファイルに分類
        py_files = [f for f in files if f.endswith(".py")]
        ts_js_files = [
            f for f in files if f.endswith((".ts", ".tsx", ".js", ".jsx"))
        ]

        # ruff format: Pythonファイル
        if py_files:
            if self._command_exists("ruff"):
                try:
                    fixes = self._run_ruff_format(py_files)
                    for fix_entry in fixes:
                        result["fixes"].append(fix_entry)
                        file_path = fix_entry["file"]
                        if file_path not in result["fixed_files"]:
                            result["fixed_files"].append(file_path)
                    logger.info(
                        "ruff format: %d file(s) fixed", len(fixes)
                    )
                except Exception as e:
                    logger.warning("ruff format execution failed: %s", e)
                    for f in py_files:
                        if f not in result["failed"]:
                            result["failed"].append(f)
            else:
                logger.info(
                    "ruff not available, skipping Python format fixes"
                )

        # eslint --fix: TypeScript/JavaScriptファイル
        if ts_js_files:
            if self._command_exists("eslint") or self._npx_available("eslint"):
                try:
                    fixes = self._run_eslint_fix(ts_js_files)
                    for fix_entry in fixes:
                        result["fixes"].append(fix_entry)
                        file_path = fix_entry["file"]
                        if file_path not in result["fixed_files"]:
                            result["fixed_files"].append(file_path)
                    logger.info(
                        "eslint --fix: %d file(s) fixed", len(fixes)
                    )
                except Exception as e:
                    logger.warning("eslint --fix execution failed: %s", e)
                    for f in ts_js_files:
                        if f not in result["failed"]:
                            result["failed"].append(f)
            else:
                logger.info(
                    "eslint not available, skipping JS/TS format fixes"
                )

        result["fixed_count"] = len(result["fixed_files"])

        logger.info(
            "AutoFixer complete: fixed=%d, failed=%d",
            result["fixed_count"],
            len(result["failed"]),
        )

        return result

    # ------------------------------------------------------------------
    # Private: ツール実行メソッド
    # ------------------------------------------------------------------

    def _run_ruff_format(self, files: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """ruff format を実行して Python ファイルをフォーマットする。

        修正前の内容を記録し、修正実行後に diff を生成する。
        修正失敗時には元ファイルを復元する。

        Args:
            files: 修正対象のPythonファイルパスリスト。
                   Noneの場合は空リスト扱い（BUG_001対策）。

        Returns:
            修正詳細のリスト。各要素は辞書で以下のキーを含む:
            - file: ファイルパス
            - tool: "ruff format"
            - description: 修正内容の説明
            - diff: unified diff形式の差分
        """
        if files is None:
            files = []

        fixes: List[Dict[str, Any]] = []

        # 各ファイルの修正前内容を記録
        before_contents: Dict[str, str] = {}
        for file_path in files:
            try:
                full_path = self._resolve_path(file_path)
                before_contents[file_path] = full_path.read_text(
                    encoding="utf-8"
                )
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(
                    "Failed to read file before fix: %s (%s)", file_path, e
                )
                continue

        if not before_contents:
            return fixes

        # ruff format 実行
        target_files = list(before_contents.keys())
        cmd = ["ruff", "format"] + target_files
        logger.debug("Running ruff format: %s", " ".join(cmd))

        try:
            proc = self._run_subprocess(cmd)
        except RuntimeError as e:
            # タイムアウトやコマンド未検出の場合はファイル復元不要
            # （ruff formatが途中でファイルを壊す可能性は低いが念のため）
            logger.warning("ruff format subprocess failed: %s", e)
            raise

        if proc.returncode != 0:
            logger.warning(
                "ruff format returned exit code %d: %s",
                proc.returncode,
                proc.stderr,
            )
            # 修正失敗: 元ファイルを復元
            for file_path, content in before_contents.items():
                self._restore_file(file_path, content)
            raise RuntimeError(
                f"ruff format failed with exit code {proc.returncode}: "
                f"{proc.stderr}"
            )

        # 修正後の内容と比較し、差分を生成
        for file_path, before in before_contents.items():
            try:
                full_path = self._resolve_path(file_path)
                after = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(
                    "Failed to read file after fix: %s (%s)", file_path, e
                )
                # 読み取り失敗: 復元を試みる
                self._restore_file(file_path, before)
                continue

            if before != after:
                diff = self._capture_diff(file_path, before, after)
                fixes.append(
                    {
                        "file": file_path,
                        "tool": "ruff format",
                        "description": "Python code formatted by ruff",
                        "diff": diff,
                    }
                )

        return fixes

    def _run_eslint_fix(self, files: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """eslint --fix を実行して JS/TS ファイルの問題を自動修正する。

        修正前の内容を記録し、修正実行後に diff を生成する。
        修正失敗時には元ファイルを復元する。

        Args:
            files: 修正対象のJS/TSファイルパスリスト。
                   Noneの場合は空リスト扱い（BUG_001対策）。

        Returns:
            修正詳細のリスト。各要素は辞書で以下のキーを含む:
            - file: ファイルパス
            - tool: "eslint --fix"
            - description: 修正内容の説明
            - diff: unified diff形式の差分
        """
        if files is None:
            files = []

        fixes: List[Dict[str, Any]] = []

        # 各ファイルの修正前内容を記録
        before_contents: Dict[str, str] = {}
        for file_path in files:
            try:
                full_path = self._resolve_path(file_path)
                before_contents[file_path] = full_path.read_text(
                    encoding="utf-8"
                )
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(
                    "Failed to read file before fix: %s (%s)", file_path, e
                )
                continue

        if not before_contents:
            return fixes

        # eslint --fix 実行
        target_files = list(before_contents.keys())
        if self._command_exists("eslint"):
            cmd = ["eslint", "--fix"] + target_files
        else:
            cmd = ["npx", "eslint", "--fix"] + target_files

        logger.debug("Running eslint --fix: %s", " ".join(cmd))

        try:
            proc = self._run_subprocess(cmd)
        except RuntimeError as e:
            logger.warning("eslint --fix subprocess failed: %s", e)
            # eslint --fix は途中でファイルを変更する可能性があるため復元
            for file_path, content in before_contents.items():
                self._restore_file(file_path, content)
            raise

        # eslint --fix は修正を適用した上で、残った問題について exit code 1 を返す。
        # exit code 0: 全問題修正済み、exit code 1: 一部問題残存、exit code 2: 設定エラー等
        if proc.returncode == 2:
            logger.warning(
                "eslint --fix returned exit code 2 (config error): %s",
                proc.stderr,
            )
            # 設定エラー: 元ファイルを復元
            for file_path, content in before_contents.items():
                self._restore_file(file_path, content)
            raise RuntimeError(
                f"eslint --fix failed with exit code 2: {proc.stderr}"
            )

        # 修正後の内容と比較し、差分を生成
        for file_path, before in before_contents.items():
            try:
                full_path = self._resolve_path(file_path)
                after = full_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                logger.warning(
                    "Failed to read file after fix: %s (%s)", file_path, e
                )
                self._restore_file(file_path, before)
                continue

            if before != after:
                diff = self._capture_diff(file_path, before, after)
                fixes.append(
                    {
                        "file": file_path,
                        "tool": "eslint --fix",
                        "description": "JS/TS code fixed by eslint",
                        "diff": diff,
                    }
                )

        return fixes

    # ------------------------------------------------------------------
    # Private: ユーティリティ
    # ------------------------------------------------------------------

    def _capture_diff(
        self, file_path: str, before_content: str, after_content: str
    ) -> str:
        """修正前後のunified diffを生成する。

        Args:
            file_path: 対象ファイルのパス（diffヘッダーに使用）
            before_content: 修正前のファイル内容
            after_content: 修正後のファイル内容

        Returns:
            unified diff形式の文字列。変更がない場合は空文字列。
        """
        before_lines = before_content.splitlines(keepends=True)
        after_lines = after_content.splitlines(keepends=True)

        diff_lines = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )

        return "".join(diff_lines)

    def _resolve_path(self, file_path: str) -> Path:
        """ファイルパスを絶対パスに解決する。

        相対パスの場合はproject_rootからの相対として解決する。
        既に絶対パスの場合はそのまま返す。

        Args:
            file_path: 解決するファイルパス

        Returns:
            解決済みの Path オブジェクト
        """
        path = Path(file_path)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _restore_file(self, file_path: str, content: str) -> None:
        """ファイルの内容を復元する。

        Args:
            file_path: 復元対象のファイルパス
            content: 復元する内容
        """
        try:
            full_path = self._resolve_path(file_path)
            full_path.write_text(content, encoding="utf-8")
            logger.info("Restored file: %s", file_path)
        except OSError as e:
            logger.error(
                "Failed to restore file: %s (%s)", file_path, e
            )

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

    def _run_subprocess(self, cmd: List[str]) -> subprocess.CompletedProcess:
        """サブプロセスを実行する。タイムアウト付き。

        Args:
            cmd: 実行するコマンドと引数のリスト

        Returns:
            subprocess.CompletedProcess オブジェクト

        Raises:
            RuntimeError: タイムアウト発生時、またはコマンド未検出時
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
