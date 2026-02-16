#!/usr/bin/env python3
"""
AI PM Framework - SQL Safety Checker
Version: 1.0.0

破壊的SQL操作を検出し、警告を出すユーティリティ。
Worker実行中に危険なDB操作が行われないよう監視する。

Usage:
    from utils.sql_safety import DestructiveSqlDetector, check_code_for_destructive_sql

    detector = DestructiveSqlDetector()
    result = detector.scan_file("path/to/script.py")
    if result.has_destructive_operations:
        print(f"警告: 破壊的SQL検出 - {result.destructive_operations}")
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Set


@dataclass
class DestructiveSqlPattern:
    """破壊的SQL操作のパターン定義"""
    pattern: str  # 正規表現パターン
    severity: str  # "CRITICAL" | "HIGH" | "MEDIUM"
    description: str  # 説明
    examples: List[str] = field(default_factory=list)


# 破壊的SQL操作パターン定義
DESTRUCTIVE_SQL_PATTERNS = [
    DestructiveSqlPattern(
        pattern=r'\bDROP\s+TABLE\s+(?!IF\s+EXISTS\s+.*_tmp\b)(?!IF\s+EXISTS\s+.*_backup\b)',
        severity="CRITICAL",
        description="テーブル削除（一時テーブル・バックアップテーブル以外）",
        examples=[
            "DROP TABLE users",
            "DROP TABLE IF EXISTS tasks",
            "DROP TABLE old_data"
        ]
    ),
    DestructiveSqlPattern(
        pattern=r'\bALTER\s+TABLE\s+\w+\s+DROP\s+COLUMN\b',
        severity="CRITICAL",
        description="カラム削除",
        examples=[
            "ALTER TABLE tasks DROP COLUMN status",
            "ALTER TABLE users DROP COLUMN email"
        ]
    ),
    DestructiveSqlPattern(
        pattern=r'\bTRUNCATE\s+TABLE\b',
        severity="CRITICAL",
        description="テーブルデータ全削除",
        examples=[
            "TRUNCATE TABLE logs",
            "TRUNCATE TABLE temp_data"
        ]
    ),
    DestructiveSqlPattern(
        pattern=r'\bDELETE\s+FROM\s+\w+\s*(?:;|$)(?!\s*WHERE)',
        severity="HIGH",
        description="WHERE句なしの全行削除",
        examples=[
            "DELETE FROM tasks",
            "DELETE FROM users;"
        ]
    ),
    DestructiveSqlPattern(
        pattern=r'\bDROP\s+DATABASE\b',
        severity="CRITICAL",
        description="データベース削除",
        examples=[
            "DROP DATABASE aipm",
            "DROP DATABASE IF EXISTS old_db"
        ]
    ),
    DestructiveSqlPattern(
        pattern=r'\bALTER\s+TABLE\s+\w+\s+RENAME\s+TO\b',
        severity="HIGH",
        description="テーブル名変更（FK/VIEW参照への波及リスク）",
        examples=[
            "ALTER TABLE tasks RENAME TO tasks_old",
            "ALTER TABLE users RENAME TO users_backup"
        ]
    ),
    DestructiveSqlPattern(
        pattern=r'\bPRAGMA\s+foreign_keys\s*=\s*(?:OFF|0)\b',
        severity="MEDIUM",
        description="外部キー制約の無効化（CASCADE削除リスク）",
        examples=[
            "PRAGMA foreign_keys = OFF",
            "PRAGMA foreign_keys = 0"
        ]
    ),
    DestructiveSqlPattern(
        pattern=r'\bUPDATE\s+\w+\s+SET\s+(?:(?!WHERE).)*[;"]\s*\)',
        severity="MEDIUM",
        description="WHERE句なしの全行更新",
        examples=[
            'cursor.execute("UPDATE tasks SET status = \'DONE\'")',
            'cursor.execute("UPDATE users SET active = 0;")'
        ]
    ),
]


@dataclass
class DestructiveSqlMatch:
    """破壊的SQL検出結果"""
    pattern: DestructiveSqlPattern
    line_number: int
    line_content: str
    file_path: Optional[str] = None


@dataclass
class ScanResult:
    """スキャン結果"""
    file_path: Optional[str] = None
    matches: List[DestructiveSqlMatch] = field(default_factory=list)
    total_lines_scanned: int = 0

    @property
    def has_destructive_operations(self) -> bool:
        """破壊的操作が検出されたか"""
        return len(self.matches) > 0

    @property
    def destructive_operations(self) -> List[str]:
        """検出された破壊的操作のリスト"""
        return [m.pattern.description for m in self.matches]

    @property
    def critical_count(self) -> int:
        """CRITICAL レベルの検出数"""
        return sum(1 for m in self.matches if m.pattern.severity == "CRITICAL")

    @property
    def high_count(self) -> int:
        """HIGH レベルの検出数"""
        return sum(1 for m in self.matches if m.pattern.severity == "HIGH")

    @property
    def medium_count(self) -> int:
        """MEDIUM レベルの検出数"""
        return sum(1 for m in self.matches if m.pattern.severity == "MEDIUM")

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "file_path": self.file_path,
            "has_destructive_operations": self.has_destructive_operations,
            "total_matches": len(self.matches),
            "critical_count": self.critical_count,
            "high_count": self.high_count,
            "medium_count": self.medium_count,
            "matches": [
                {
                    "severity": m.pattern.severity,
                    "description": m.pattern.description,
                    "line_number": m.line_number,
                    "line_content": m.line_content.strip(),
                }
                for m in self.matches
            ]
        }


class DestructiveSqlDetector:
    """
    破壊的SQL操作の検出器

    ファイルまたはコード文字列をスキャンし、破壊的なSQL操作を検出する。
    """

    def __init__(
        self,
        patterns: Optional[List[DestructiveSqlPattern]] = None,
        ignore_comments: bool = True,
    ):
        """
        Args:
            patterns: 検出パターンリスト（Noneの場合はデフォルトパターンを使用）
            ignore_comments: コメント行を無視するか（デフォルト: True）
        """
        self.patterns = patterns if patterns is not None else DESTRUCTIVE_SQL_PATTERNS
        self.ignore_comments = ignore_comments

    def scan_file(self, file_path: Path | str) -> ScanResult:
        """
        ファイルをスキャンして破壊的SQL操作を検出

        Args:
            file_path: スキャン対象のファイルパス

        Returns:
            ScanResult: スキャン結果
        """
        file_path = Path(file_path)

        if not file_path.exists():
            return ScanResult(file_path=str(file_path), total_lines_scanned=0)

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            # ファイル読み取りエラー時は空結果を返す
            return ScanResult(file_path=str(file_path), total_lines_scanned=0)

        result = self.scan_code(content)
        result.file_path = str(file_path)

        # マッチ結果にファイルパスを設定
        for match in result.matches:
            match.file_path = str(file_path)

        return result

    def scan_code(self, code: str) -> ScanResult:
        """
        コード文字列をスキャンして破壊的SQL操作を検出

        Args:
            code: スキャン対象のコード

        Returns:
            ScanResult: スキャン結果
        """
        lines = code.split("\n")
        matches = []
        in_multiline_comment = False

        for line_num, line in enumerate(lines, start=1):
            # 複数行コメントの処理
            if self.ignore_comments:
                # 複数行コメント開始
                if "/*" in line:
                    in_multiline_comment = True
                # 複数行コメント終了
                if "*/" in line:
                    in_multiline_comment = False
                    continue
                # 複数行コメント中はスキップ
                if in_multiline_comment:
                    continue
                # 単一行コメントをスキップ
                if self._is_comment_line(line):
                    continue

            # 各パターンでマッチング
            for pattern in self.patterns:
                if re.search(pattern.pattern, line, re.IGNORECASE):
                    matches.append(DestructiveSqlMatch(
                        pattern=pattern,
                        line_number=line_num,
                        line_content=line,
                    ))

        return ScanResult(
            matches=matches,
            total_lines_scanned=len(lines),
        )

    def _is_comment_line(self, line: str) -> bool:
        """
        行がコメント行かどうかを判定

        Args:
            line: 判定対象の行

        Returns:
            bool: コメント行の場合True
        """
        stripped = line.strip()

        # Python/Shell コメント
        if stripped.startswith("#"):
            return True

        # SQL コメント
        if stripped.startswith("--"):
            return True

        # C/Java/JS スタイルコメント
        if stripped.startswith("//"):
            return True

        # 複数行コメント（簡易判定）
        if stripped.startswith("/*") or stripped.startswith("*/"):
            return True

        return False

    def scan_directory(
        self,
        dir_path: Path | str,
        extensions: Optional[Set[str]] = None,
        recursive: bool = True,
    ) -> List[ScanResult]:
        """
        ディレクトリ内のファイルをスキャン

        Args:
            dir_path: スキャン対象のディレクトリパス
            extensions: スキャン対象の拡張子セット（例: {".py", ".sql"}）
            recursive: 再帰的にスキャンするか

        Returns:
            List[ScanResult]: 各ファイルのスキャン結果リスト
        """
        dir_path = Path(dir_path)

        if not dir_path.exists() or not dir_path.is_dir():
            return []

        if extensions is None:
            extensions = {".py", ".sql", ".sh", ".js", ".ts"}

        results = []

        # ファイル列挙
        pattern = "**/*" if recursive else "*"
        for file_path in dir_path.glob(pattern):
            if not file_path.is_file():
                continue

            if file_path.suffix not in extensions:
                continue

            result = self.scan_file(file_path)
            if result.has_destructive_operations:
                results.append(result)

        return results


def check_code_for_destructive_sql(code: str) -> Dict[str, Any]:
    """
    コード文字列に破壊的SQL操作が含まれているかをチェック

    簡易インターフェース関数。

    Args:
        code: チェック対象のコード

    Returns:
        Dict containing:
            - has_destructive_sql: bool
            - count: int
            - operations: List[str]

    Example:
        result = check_code_for_destructive_sql("DROP TABLE users")
        if result["has_destructive_sql"]:
            print(f"警告: {result['operations']}")
    """
    detector = DestructiveSqlDetector()
    scan_result = detector.scan_code(code)

    return {
        "has_destructive_sql": scan_result.has_destructive_operations,
        "count": len(scan_result.matches),
        "critical_count": scan_result.critical_count,
        "high_count": scan_result.high_count,
        "medium_count": scan_result.medium_count,
        "operations": scan_result.destructive_operations,
        "details": scan_result.to_dict(),
    }


def check_file_for_destructive_sql(file_path: Path | str) -> Dict[str, Any]:
    """
    ファイルに破壊的SQL操作が含まれているかをチェック

    簡易インターフェース関数。

    Args:
        file_path: チェック対象のファイルパス

    Returns:
        Dict containing:
            - has_destructive_sql: bool
            - count: int
            - operations: List[str]
            - file_path: str

    Example:
        result = check_file_for_destructive_sql("migrations/drop_old_tables.py")
        if result["has_destructive_sql"]:
            print(f"警告: {result['file_path']} に破壊的SQL検出")
    """
    detector = DestructiveSqlDetector()
    scan_result = detector.scan_file(file_path)

    return {
        "has_destructive_sql": scan_result.has_destructive_operations,
        "count": len(scan_result.matches),
        "critical_count": scan_result.critical_count,
        "high_count": scan_result.high_count,
        "medium_count": scan_result.medium_count,
        "operations": scan_result.destructive_operations,
        "file_path": scan_result.file_path,
        "details": scan_result.to_dict(),
    }


if __name__ == "__main__":
    # テスト実行
    import sys

    print("SQL Safety Checker - Test")

    # テストコード
    test_code = """
    # マイグレーションスクリプト
    cursor.execute("DROP TABLE old_users")
    cursor.execute("ALTER TABLE tasks DROP COLUMN deprecated_field")
    cursor.execute("PRAGMA foreign_keys = OFF")
    cursor.execute("DELETE FROM logs WHERE created_at < '2020-01-01'")  # これはOK（WHERE句あり）
    cursor.execute("DELETE FROM temp_table")  # これは警告
    """

    result = check_code_for_destructive_sql(test_code)

    print(f"\n破壊的SQL検出結果:")
    print(f"  検出: {result['has_destructive_sql']}")
    print(f"  件数: {result['count']}")
    print(f"  CRITICAL: {result['critical_count']}")
    print(f"  HIGH: {result['high_count']}")
    print(f"  MEDIUM: {result['medium_count']}")

    if result['has_destructive_sql']:
        print(f"\n検出された操作:")
        for op in result['operations']:
            print(f"  - {op}")

        print(f"\n詳細:")
        for match in result['details']['matches']:
            print(f"  [{match['severity']}] Line {match['line_number']}: {match['description']}")
            print(f"    → {match['line_content']}")
