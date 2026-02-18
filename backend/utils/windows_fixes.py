#!/usr/bin/env python3
"""
AI PM Framework - Windows固有問題の恒久対応

Windows環境で発生する以下の問題を修正:
1. stdin/stdout/stderr encoding問題（UTF-8強制）
2. better-sqlite3 rebuild（起動時チェック＋自動rebuild）
3. depends_on型不一致（int/str統一）
"""

import io
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

logger = logging.getLogger(__name__)


def fix_stdio_encoding():
    """
    Windows環境でstdin/stdout/stderrをUTF-8に強制設定

    config.py の setup_utf8_output() は stdout/stderr のみ。
    この関数は stdin も含めて設定する。
    """
    if sys.platform != "win32":
        return

    # stdin
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(encoding='utf-8')
    elif hasattr(sys.stdin, 'buffer'):
        sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')

    # stdout
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    elif hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

    # stderr
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    elif hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    # Also set environment variable for child processes
    os.environ['PYTHONIOENCODING'] = 'utf-8'

    logger.debug("stdio encoding set to UTF-8")


def check_better_sqlite3(app_dir=None):
    """
    better-sqlite3の動作確認と自動rebuild

    Args:
        app_dir: Electronアプリのディレクトリ（デフォルト: PROJECTS/ai_pm_manager）

    Returns:
        dict with keys: ok (bool), message (str), rebuilt (bool)
    """
    if app_dir is None:
        # Electronアプリのnode_modules確認用 - 実行環境ルート
        app_dir = _project_root

    app_dir = Path(app_dir)
    node_modules = app_dir / "node_modules"

    result = {"ok": False, "message": "", "rebuilt": False}

    if not node_modules.exists():
        result["message"] = f"node_modules not found at {node_modules}"
        return result

    better_sqlite3_dir = node_modules / "better-sqlite3"
    if not better_sqlite3_dir.exists():
        result["message"] = "better-sqlite3 not installed"
        return result

    # Check if better-sqlite3 is working by trying to require it
    try:
        check_script = "try { require('better-sqlite3'); console.log('OK'); } catch(e) { console.log('FAIL:' + e.message); }"
        proc = subprocess.run(
            ["node", "-e", check_script],
            capture_output=True, text=True, timeout=10,
            cwd=str(app_dir)
        )

        if proc.stdout.strip() == "OK":
            result["ok"] = True
            result["message"] = "better-sqlite3 is working"
            return result

        logger.warning(f"better-sqlite3 check failed: {proc.stdout.strip()}")

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning(f"better-sqlite3 check error: {e}")

    # Attempt rebuild
    logger.info("Attempting to rebuild better-sqlite3...")
    try:
        # Try electron-rebuild first
        rebuild_cmd = None

        npx_path = app_dir / "node_modules" / ".bin" / "electron-rebuild"
        if npx_path.exists() or (npx_path.with_suffix(".cmd")).exists():
            rebuild_cmd = ["npx", "electron-rebuild", "-f", "-w", "better-sqlite3"]
        else:
            # Fallback to npm rebuild
            rebuild_cmd = ["npm", "rebuild", "better-sqlite3"]

        proc = subprocess.run(
            rebuild_cmd,
            capture_output=True, text=True, timeout=120,
            cwd=str(app_dir),
            shell=(sys.platform == "win32")  # shell=True on Windows for npx/npm
        )

        if proc.returncode == 0:
            result["ok"] = True
            result["rebuilt"] = True
            result["message"] = "better-sqlite3 rebuilt successfully"
            logger.info("better-sqlite3 rebuilt successfully")
        else:
            result["message"] = f"Rebuild failed: {proc.stderr[:200]}"
            logger.error(f"better-sqlite3 rebuild failed: {proc.stderr[:200]}")

    except Exception as e:
        result["message"] = f"Rebuild error: {e}"
        logger.error(f"better-sqlite3 rebuild error: {e}")

    return result


def fix_depends_on_types():
    """
    task_dependenciesテーブルのdepends_on_task_idを文字列型に統一

    int型で格納されている場合は "TASK_{id}" 形式に変換する。

    Returns:
        dict: fixed_count (int), errors (list)
    """
    from utils.db import get_connection

    result = {"fixed_count": 0, "errors": []}

    conn = get_connection()
    try:
        cursor = conn.cursor()

        # Find rows where depends_on_task_id looks like an integer (no "TASK_" prefix)
        cursor.execute("""
            SELECT rowid, task_id, depends_on_task_id, project_id
            FROM task_dependencies
            WHERE depends_on_task_id NOT LIKE 'TASK_%'
        """)

        rows = cursor.fetchall()

        for row in rows:
            rowid = row[0]
            task_id = row[1]
            dep_id = row[2]
            project_id = row[3]

            # Convert to proper TASK_XXX format
            try:
                # If it's a number (stored as string or int), convert
                numeric_id = int(str(dep_id).strip())
                new_dep_id = f"TASK_{numeric_id}"

                # Verify the target task exists
                cursor.execute(
                    "SELECT id FROM tasks WHERE id = ? AND project_id = ?",
                    (new_dep_id, project_id)
                )

                if cursor.fetchone():
                    cursor.execute(
                        "UPDATE task_dependencies SET depends_on_task_id = ? WHERE rowid = ?",
                        (new_dep_id, rowid)
                    )
                    result["fixed_count"] += 1
                    logger.info(f"Fixed dependency: {task_id} -> {dep_id} => {new_dep_id}")
                else:
                    result["errors"].append(
                        f"Target task {new_dep_id} not found for dependency of {task_id}"
                    )

            except ValueError:
                result["errors"].append(
                    f"Cannot parse depends_on_task_id '{dep_id}' for {task_id}"
                )

        conn.commit()
        logger.info(f"Fixed {result['fixed_count']} dependency type issues")

    except Exception as e:
        result["errors"].append(str(e))
        logger.error(f"fix_depends_on_types error: {e}")
    finally:
        conn.close()

    return result


def apply_all_fixes(check_sqlite3=True, fix_deps=True):
    """
    全てのWindows固有修正を適用

    Args:
        check_sqlite3: better-sqlite3チェックを実行するか
        fix_deps: depends_on型修正を実行するか

    Returns:
        dict: 各修正の結果
    """
    results = {}

    # 1. encoding fix (always apply on Windows)
    fix_stdio_encoding()
    results["encoding"] = {"applied": sys.platform == "win32"}

    # 2. better-sqlite3 check
    if check_sqlite3:
        results["better_sqlite3"] = check_better_sqlite3()

    # 3. depends_on type fix
    if fix_deps:
        results["depends_on"] = fix_depends_on_types()

    return results


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Windows固有問題の修正")
    parser.add_argument("--encoding", action="store_true", help="encoding修正のみ")
    parser.add_argument("--sqlite3", action="store_true", help="better-sqlite3チェックのみ")
    parser.add_argument("--deps", action="store_true", help="depends_on型修正のみ")
    parser.add_argument("--all", action="store_true", help="全修正を適用")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )

    if args.all or not (args.encoding or args.sqlite3 or args.deps):
        results = apply_all_fixes()
    else:
        results = {}
        if args.encoding:
            fix_stdio_encoding()
            results["encoding"] = {"applied": True}
        if args.sqlite3:
            results["better_sqlite3"] = check_better_sqlite3()
        if args.deps:
            results["depends_on"] = fix_depends_on_types()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    else:
        for key, value in results.items():
            print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
