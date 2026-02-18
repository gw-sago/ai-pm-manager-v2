#!/usr/bin/env python3
"""
AI PM Framework - マスターデータ補完ユーティリティ

既存DBに対してstatus_transitions等のマスターデータが不足している場合に
schema_v2.sqlのINSERT OR IGNORE文を再適用して補完する。

Electron側の ensureSchemaAndSeedData() と同等の機能をPython側で提供。

Usage:
    python backend/utils/ensure_master_data.py [--json] [--verbose]
"""

import json
import sys
from pathlib import Path

# backend/ をパスに追加
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.db_config import get_db_config, setup_utf8_output
from utils.db import get_connection, close_connection, fetch_one


def ensure_master_data(db_path=None, schema_path=None, verbose=False):
    """
    既存DBのマスターデータ（status_transitions等）を補完する

    CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE により安全に実行可能。
    既存データは上書きされない。

    Args:
        db_path: DBファイルパス（Noneでデフォルト）
        schema_path: スキーマファイルパス（Noneでデフォルト）
        verbose: 詳細ログ出力

    Returns:
        dict: { success, before_count, after_count, added, message }
    """
    config = get_db_config()
    if db_path is None:
        db_path = config.db_path
    if schema_path is None:
        schema_path = config.schema_path

    schema_path = Path(schema_path)
    if not schema_path.exists():
        return {
            "success": False,
            "message": f"スキーマファイルが見つかりません: {schema_path}",
            "before_count": 0,
            "after_count": 0,
            "added": 0,
        }

    conn = get_connection(db_path)
    try:
        # 補完前の行数を取得
        row = conn.execute("SELECT COUNT(*) as cnt FROM status_transitions").fetchone()
        before_count = row["cnt"] if row else 0

        # 不足テーブルチェック
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        expected = ["orders", "tasks", "backlog_items", "status_transitions",
                     "file_locks", "incidents", "builds"]
        missing = [t for t in expected if t not in table_names]

        if before_count > 0 and not missing:
            msg = f"マスターデータは正常です（{before_count}件のstatus_transitions）"
            if verbose:
                print(f"[MasterData] {msg}")
            return {
                "success": True,
                "message": msg,
                "before_count": before_count,
                "after_count": before_count,
                "added": 0,
            }

        if verbose:
            print(f"[MasterData] 補完開始: transitions={before_count}, missing_tables={missing}")

        # スキーマ全体を再適用（CREATE TABLE IF NOT EXISTS + INSERT OR IGNORE）
        schema_sql = schema_path.read_text(encoding="utf-8")
        conn.executescript(schema_sql)

        # 補完後の行数を取得
        row = conn.execute("SELECT COUNT(*) as cnt FROM status_transitions").fetchone()
        after_count = row["cnt"] if row else 0
        added = after_count - before_count

        msg = f"マスターデータ補完完了: {before_count}→{after_count}件（{added}件追加）"
        if verbose:
            print(f"[MasterData] {msg}")

        return {
            "success": True,
            "message": msg,
            "before_count": before_count,
            "after_count": after_count,
            "added": added,
        }

    except Exception as e:
        msg = f"マスターデータ補完に失敗: {e}"
        if verbose:
            print(f"[MasterData] {msg}", file=sys.stderr)
        return {
            "success": False,
            "message": msg,
            "before_count": 0,
            "after_count": 0,
            "added": 0,
        }
    finally:
        close_connection(conn)


def main():
    setup_utf8_output()

    import argparse
    parser = argparse.ArgumentParser(description="マスターデータ補完ユーティリティ")
    parser.add_argument("--json", action="store_true", help="JSON出力")
    parser.add_argument("--verbose", action="store_true", help="詳細ログ")
    args = parser.parse_args()

    result = ensure_master_data(verbose=not args.json or args.verbose)

    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(result["message"])

    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
