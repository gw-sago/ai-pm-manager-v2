#!/usr/bin/env python3
"""
AI PM Framework - 統合リリーススクリプト

ORDER完了 -> BACKLOG更新 -> RELEASE_LOG記録 -> git add/commit を1コマンドで実行。

Usage:
    # 単一ORDER
    python backend/release/git_release.py PROJECT_ID ORDER_ID [OPTIONS]

    # 複数ORDER
    python backend/release/git_release.py PROJECT_ID --multi ORDER_099,ORDER_100 [OPTIONS]

Options:
    --dry-run         変更を行わない（確認のみ）
    --skip-complete   ORDER完了処理をスキップ
    --skip-backlog    BACKLOG更新をスキップ
    --skip-log        RELEASE_LOG記録をスキップ
    --skip-git        gitコミットをスキップ
    --skip-migration  マイグレーション実行をスキップ
    --skip-build      ビルド実行をスキップ
    --extra-files F   追加ステージング対象（カンマ区切り）
    --message MSG     コミットメッセージカスタマイズ
    --json            JSON出力

Workflow:
    1. ORDER状態検証（全タスクCOMPLETED/DONE確認）
    2. マイグレーション実行（破壊的DB変更を含む場合のみ）
    3. ORDER完了処理（complete_order）
    4. 関連BACKLOG → DONE更新
    5. RELEASE_LOG.md記録
    6. git add → git commit
    7. ビルド実行（Electronアプリ等、ビルド設定がある場合のみ）
"""

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 親パッケージからインポート
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import setup_utf8_output
from utils.db import get_connection, fetch_all, fetch_one
from release.execute_release import (
    detect_migrations,
    execute_migration_build_deploy,
)

setup_utf8_output()

# ============================================================================
# ステージング対象パターン
# ============================================================================

INCLUDE_PATTERNS = [
    # フレームワーク本体
    "backend/**",
    ".claude/commands/**",
    "TEMPLATE/**",
    # プロジェクト成果物
    "PROJECTS/*/RESULT/ORDER_*/01_GOAL*",
    "PROJECTS/*/RESULT/ORDER_*/02_REQUIREMENTS*",
    "PROJECTS/*/RESULT/ORDER_*/03_STAFFING*",
    "PROJECTS/*/RESULT/ORDER_*/05_REPORT/**",
    "PROJECTS/*/RESULT/ORDER_*/06_ARTIFACTS/**",
    "PROJECTS/*/RESULT/ORDER_*/07_REVIEW/**",
    "PROJECTS/*/RESULT/ORDER_*/08_ESCALATIONS/**",
    # プロジェクト設定
    "PROJECTS/*/ORDERS/**",
    "PROJECTS/*/RELEASE_LOG.md",
    "PROJECTS/*/PROJECT_INFO*",
    "PROJECTS/*/PROJECT_INFO/**",
    "PROJECTS/*/DASHBOARD/**",
    "PROJECTS/*/README.md",
    "PROJECTS/*/CLAUDE.md",
    # ルートファイル
    ".gitignore",
    "CLAUDE.md",
]

EXCLUDE_PATTERNS = [
    # 一時ファイル
    "tmp_*",
    "**/tmp_*",
    "**/files_state_*.json",
    # 作業中ディレクトリ
    "PROJECTS/*/DEV/**",
    "PROJECTS/*/RESULT/*/04_QUEUE/**",
    "PROJECTS/*/RESULT/*/WORK/**",
    # DB・データ
    "data/**",
    "*.db",
    # セッション
    "**/SESSION.md",
    # 環境固有
    ".env",
    ".env.*",
    ".claude/settings.local.json",
    # Python
    "**/__pycache__/**",
    "*.pyc",
]

# 不正パス検出用の正規表現パターン（ドライブレター、オクタルエスケープ等）
INVALID_PATH_PATTERNS = [
    r"^[A-Z]:",  # ドライブレター（D:, C: 等）
    r"\\[0-3][0-7]{2}",  # オクタルエスケープシーケンス（\357 等）
]


# ============================================================================
# ファイルパターンマッチング
# ============================================================================

def _matches_any_pattern(filepath: str, patterns: List[str]) -> bool:
    """ファイルパスがパターンリストのいずれかにマッチするか判定"""
    filepath_posix = filepath.replace("\\", "/")
    for pattern in patterns:
        # ** を含むパターン
        if "**" in pattern:
            # fnmatch は ** を直接サポートしないので段階的にチェック
            base_pattern = pattern.replace("**", "*")
            if fnmatch.fnmatch(filepath_posix, base_pattern):
                return True
            # ディレクトリプレフィックスでもチェック
            prefix = pattern.split("**")[0].rstrip("/")
            if prefix and filepath_posix.startswith(prefix + "/"):
                return True
        elif fnmatch.fnmatch(filepath_posix, pattern):
            return True
        # パスの末尾コンポーネントでもチェック
        basename = filepath_posix.split("/")[-1]
        if fnmatch.fnmatch(basename, pattern):
            return True
    return False


def should_stage_file(filepath: str) -> bool:
    """ファイルをステージング対象にすべきか判定"""
    # 不正パターンに一致 → 対象外（ドライブレター、オクタルエスケープ等）
    for pattern in INVALID_PATH_PATTERNS:
        if re.search(pattern, filepath):
            return False
    # 除外パターンに一致 → 対象外
    if _matches_any_pattern(filepath, EXCLUDE_PATTERNS):
        return False
    # 包含パターンに一致 → 対象
    if _matches_any_pattern(filepath, INCLUDE_PATTERNS):
        return True
    return False


# ============================================================================
# Git操作
# ============================================================================

def _get_ai_pm_root() -> Path:
    """AI PMフレームワークのルートディレクトリを取得"""
    # このスクリプトは backend/release/ にある
    return Path(__file__).resolve().parent.parent.parent


def collect_stageable_files(ai_pm_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    git statusから変更ファイルを取得し、ステージング対象をフィルタリング

    Returns:
        {"files": [...], "excluded": [...], "total_changed": int}
    """
    if ai_pm_root is None:
        ai_pm_root = _get_ai_pm_root()

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True,
        cwd=str(ai_pm_root),
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        return {"files": [], "excluded": [], "total_changed": 0,
                "error": f"git status failed: {result.stderr}"}

    def _decode_git_quoted_path(quoted_path: str) -> str:
        """gitのクォートされたパス内のオクタルエスケープ(\\NNN)をデコード"""
        def _octal_replace(m):
            return bytes([int(m.group(1), 8)])
        try:
            raw = re.sub(
                rb"\\([0-3][0-7]{2})",
                _octal_replace,
                quoted_path.encode("latin-1"),
            )
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return quoted_path  # デコード失敗時は元のパスを使用

    all_files = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        # git status --porcelain: XY PATH (XY=2 chars, then space + path)
        # X=staged, Y=unstaged, ?? = untracked
        status_code = line[:2]
        # XY の後のパスを取得（XY後のスペース区切りを考慮）
        filepath = line[2:].lstrip(" ")
        # リネームの場合 "old -> new" 形式
        if " -> " in filepath:
            filepath = filepath.split(" -> ")[1]
        # クォートされたパスの処理（git は特殊文字を含むパスを
        # "\357\200\272path" のようにオクタルエスケープで出力する）
        if filepath.startswith('"') and filepath.endswith('"'):
            filepath = _decode_git_quoted_path(filepath[1:-1])
        all_files.append((status_code, filepath))

    staged = []
    excluded = []

    for status_code, filepath in all_files:
        if should_stage_file(filepath):
            staged.append(filepath)
        else:
            excluded.append(filepath)

    return {
        "files": staged,
        "excluded": excluded,
        "total_changed": len(all_files),
    }


def run_git_add(files: List[str], ai_pm_root: Optional[Path] = None) -> Dict[str, Any]:
    """git add を実行"""
    if ai_pm_root is None:
        ai_pm_root = _get_ai_pm_root()

    if not files:
        return {"success": True, "added": 0, "message": "No files to stage"}

    # バッチでgit add（一度に多すぎる場合は分割）
    batch_size = 50
    total_added = 0

    for i in range(0, len(files), batch_size):
        batch = files[i:i + batch_size]
        result = subprocess.run(
            ["git", "add"] + batch,
            capture_output=True, text=True,
            cwd=str(ai_pm_root),
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return {
                "success": False,
                "error": f"git add failed: {result.stderr}",
                "added": total_added,
            }
        total_added += len(batch)

    return {"success": True, "added": total_added}


def run_git_commit(message: str, ai_pm_root: Optional[Path] = None) -> Dict[str, Any]:
    """git commit を実行"""
    if ai_pm_root is None:
        ai_pm_root = _get_ai_pm_root()

    result = subprocess.run(
        ["git", "commit", "-m", message],
        capture_output=True, text=True,
        cwd=str(ai_pm_root),
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        # "nothing to commit" は成功扱い
        if "nothing to commit" in stdout or "nothing to commit" in stderr:
            return {"success": True, "commit_hash": None,
                    "message": "Nothing to commit"}
        return {
            "success": False,
            "error": f"git commit failed: {stderr or stdout}",
        }

    # コミットハッシュを取得
    log_result = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        capture_output=True, text=True,
        cwd=str(ai_pm_root),
        encoding="utf-8",
        errors="replace",
    )
    commit_hash = log_result.stdout.strip().split(" ")[0] if log_result.returncode == 0 else "unknown"

    return {
        "success": True,
        "commit_hash": commit_hash,
        "output": result.stdout.strip(),
    }


# ============================================================================
# コミットメッセージ生成
# ============================================================================

def generate_commit_message(
    order_ids: List[str],
    order_titles: Dict[str, str],
    backlog_ids: Optional[List[str]] = None,
) -> str:
    """
    リリース用コミットメッセージを自動生成

    単一ORDER: release(ORDER_119): タスク進捗のリアルタイムUI更新
    複数ORDER: release(ORDER_099-119): 未リリースN ORDER一括リリース
    """
    if len(order_ids) == 1:
        oid = order_ids[0]
        title = order_titles.get(oid, "")
        header = f"release({oid}): {title}"
    else:
        nums = sorted([int(oid.replace("ORDER_", "")) for oid in order_ids])
        header = f"release(ORDER_{nums[0]:03d}-{nums[-1]:03d}): 未リリース{len(order_ids)} ORDER一括リリース"

    lines = [header, ""]

    # ORDER詳細
    if len(order_ids) > 1:
        for oid in order_ids:
            title = order_titles.get(oid, "")
            lines.append(f"- {oid}: {title}")
        lines.append("")

    # BACKLOG情報
    if backlog_ids:
        lines.append(f"{', '.join(backlog_ids)} 完了")
        lines.append("")

    lines.append("Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>")

    return "\n".join(lines)


# ============================================================================
# マイグレーション・ビルド処理
# ============================================================================

def _check_destructive_db_changes(project_id: str, order_ids: List[str]) -> Dict[str, Any]:
    """
    破壊的DB変更を含むタスクを検出

    execute_release.detect_migrations() に委譲。

    Returns:
        検出結果とマイグレーションスクリプトパスのリスト
    """
    return detect_migrations(project_id, order_ids, _get_ai_pm_root())


def _execute_migrations(
    project_id: str,
    order_ids: List[str],
    ai_pm_root: Path,
) -> Dict[str, Any]:
    """
    マイグレーションスクリプトを実行

    execute_release.execute_migrations() に委譲。

    Returns:
        実行結果
    """
    from release.execute_release import execute_migrations
    return execute_migrations(
        project_id=project_id,
        order_ids=order_ids,
        ai_pm_root=ai_pm_root,
    )


def _execute_build(project_id: str, order_ids: List[str]) -> Dict[str, Any]:
    """
    ビルドを実行（プロジェクトにビルド設定がある場合のみ）

    execute_release.execute_build_step() に委譲。

    Returns:
        ビルド結果
    """
    from release.execute_release import execute_build_step
    return execute_build_step(
        project_id=project_id,
        order_ids=order_ids,
    )


# ============================================================================
# ORDER/BACKLOG操作
# ============================================================================

def _validate_orders(project_id: str, order_ids: List[str]) -> Dict[str, Any]:
    """ORDER状態を検証（全タスクがCOMPLETED/DONEであること）"""
    conn = get_connection()
    results = []

    for order_id in order_ids:
        # ORDER存在確認
        order = fetch_one(
            conn,
            "SELECT id, title, status FROM orders WHERE id = ? AND project_id = ?",
            (order_id, project_id),
        )
        if not order:
            conn.close()
            return {"success": False, "error": f"ORDER {order_id} not found"}

        # タスク状態確認
        tasks = fetch_all(
            conn,
            "SELECT id, status FROM tasks WHERE order_id = ? AND project_id = ?",
            (order_id, project_id),
        )

        incomplete = [
            dict(t) for t in tasks
            if t["status"] not in ("COMPLETED", "DONE", "CANCELLED", "REJECTED", "SKIPPED")
        ]

        if incomplete:
            conn.close()
            task_summary = ", ".join(f"{t['id']}({t['status']})" for t in incomplete[:5])
            return {
                "success": False,
                "error": f"ORDER {order_id} has incomplete tasks: {task_summary}",
            }

        results.append({
            "order_id": order_id,
            "title": order["title"],
            "status": order["status"],
        })

    conn.close()
    return {"success": True, "orders": results}


def _complete_orders(project_id: str, order_ids: List[str]) -> List[str]:
    """ORDER完了処理（既にCOMPLETEDならスキップ）"""
    completed = []
    try:
        from order.update import complete_order
        for order_id in order_ids:
            conn = get_connection()
            order = fetch_one(
                conn,
                "SELECT status FROM orders WHERE id = ? AND project_id = ?",
                (order_id, project_id),
            )
            conn.close()

            if order and order["status"] != "COMPLETED":
                try:
                    complete_order(project_id, order_id, render=False)
                    completed.append(order_id)
                except Exception:
                    pass  # 既にCOMPLETEDの場合など
    except ImportError:
        pass  # complete_orderが使えない場合はスキップ
    return completed


def _complete_backlogs(project_id: str, order_ids: List[str]) -> List[Dict[str, str]]:
    """関連BACKLOGをDONEに更新"""
    updated = []
    conn = get_connection()

    for order_id in order_ids:
        backlogs = fetch_all(
            conn,
            """SELECT id, title, status FROM backlog_items
               WHERE project_id = ? AND related_order_id = ?
               AND status NOT IN ('DONE', 'CANCELED')""",
            (project_id, order_id),
        )

        for bl in backlogs:
            try:
                conn.execute(
                    """UPDATE backlog_items
                       SET status = 'DONE', completed_at = datetime('now'),
                           updated_at = datetime('now')
                       WHERE id = ? AND project_id = ?""",
                    (bl["id"], project_id),
                )
                conn.execute(
                    """INSERT INTO change_history
                       (entity_type, entity_id, project_id, field_name,
                        old_value, new_value, changed_by, change_reason)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    ("backlog", bl["id"], project_id, "status",
                     bl["status"], "DONE", "System",
                     f"Related ORDER {order_id} released"),
                )
                updated.append({"id": bl["id"], "title": bl["title"],
                                "old_status": bl["status"]})
            except Exception:
                pass

    conn.commit()
    conn.close()
    return updated


def _record_release_logs(
    project_id: str,
    order_ids: List[str],
    order_titles: Dict[str, str],
    backlog_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """RELEASE_LOG.mdに記録"""
    results = []
    try:
        from release.log import record_release
        from release.detect import detect_release_targets

        for order_id in order_ids:
            try:
                # DEV→本番の差分検出
                targets = detect_release_targets(
                    project_id=project_id,
                    order_id=order_id,
                    all_dev=True,
                    include_diff=False,
                )
                files = targets.get("targets", []) if targets.get("success") else []

                title = order_titles.get(order_id, "")
                notes = title
                bl_for_order = backlog_ids if backlog_ids else None

                log_result = record_release(
                    project_id=project_id,
                    order_id=order_id,
                    files=files,
                    executor="PM (Claude Opus 4.6)",
                    notes=notes,
                    backlog_ids=bl_for_order,
                )
                results.append(log_result)
            except Exception as e:
                results.append({"success": False, "error": str(e),
                                "order_id": order_id})
    except ImportError:
        pass
    return results


# ============================================================================
# メイン実行
# ============================================================================

def execute_git_release(
    project_id: str,
    order_ids: List[str],
    *,
    dry_run: bool = False,
    skip_complete: bool = False,
    skip_backlog: bool = False,
    skip_log: bool = False,
    skip_git: bool = False,
    skip_migration: bool = False,
    skip_build: bool = False,
    extra_files: Optional[List[str]] = None,
    custom_message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    統合リリース処理を実行

    Returns:
        実行結果の辞書
    """
    ai_pm_root = _get_ai_pm_root()
    result: Dict[str, Any] = {
        "success": True,
        "project_id": project_id,
        "order_ids": order_ids,
        "dry_run": dry_run,
        "steps": {},
        "executed_at": datetime.now().isoformat(),
    }

    # Step 1: ORDER検証
    validation = _validate_orders(project_id, order_ids)
    result["steps"]["validate"] = validation
    if not validation["success"]:
        result["success"] = False
        result["error"] = validation["error"]
        return result

    order_titles = {o["order_id"]: o["title"] for o in validation["orders"]}
    result["order_titles"] = order_titles

    if dry_run:
        # ドライランの場合はステージング対象のみ表示
        staging = collect_stageable_files(ai_pm_root)
        result["steps"]["staging_preview"] = staging

        msg = custom_message or generate_commit_message(
            order_ids, order_titles,
        )
        result["steps"]["commit_message_preview"] = msg

        # 破壊的DB変更チェック（プレビュー）
        destructive_check = _check_destructive_db_changes(project_id, order_ids)
        if destructive_check.get("has_migrations"):
            result["steps"]["migration_preview"] = destructive_check

        result["message"] = "Dry run: no changes made"
        return result

    # Step 2: マイグレーション実行（破壊的DB変更を含む場合）
    if not skip_migration:
        migration_result = _execute_migrations(project_id, order_ids, ai_pm_root)
        result["steps"]["migrations"] = migration_result

        if not migration_result["success"]:
            result["success"] = False
            result["error"] = migration_result.get("error", "migration failed")
            return result

    # Step 3: ORDER完了
    if not skip_complete:
        completed = _complete_orders(project_id, order_ids)
        result["steps"]["complete_orders"] = completed

    # Step 4: BACKLOG更新
    backlog_ids = []
    if not skip_backlog:
        updated_backlogs = _complete_backlogs(project_id, order_ids)
        result["steps"]["backlog_updates"] = updated_backlogs
        backlog_ids = [bl["id"] for bl in updated_backlogs]

    # Step 5: RELEASE_LOG記録
    if not skip_log:
        log_results = _record_release_logs(
            project_id, order_ids, order_titles, backlog_ids or None,
        )
        result["steps"]["release_logs"] = log_results

    # Step 6: git add & commit
    if not skip_git:
        # ステージング対象収集
        staging = collect_stageable_files(ai_pm_root)
        result["steps"]["staging"] = staging

        files_to_add = staging["files"]

        # 追加ファイル
        if extra_files:
            files_to_add.extend(extra_files)

        if not files_to_add:
            result["steps"]["git"] = {"message": "No files to commit"}
            return result

        # git add
        add_result = run_git_add(files_to_add, ai_pm_root)
        result["steps"]["git_add"] = add_result

        if not add_result["success"]:
            result["success"] = False
            result["error"] = add_result["error"]
            return result

        # コミットメッセージ生成
        commit_msg = custom_message or generate_commit_message(
            order_ids, order_titles, backlog_ids or None,
        )

        # git commit
        commit_result = run_git_commit(commit_msg, ai_pm_root)
        result["steps"]["git_commit"] = commit_result

        if not commit_result["success"]:
            result["success"] = False
            result["error"] = commit_result.get("error", "commit failed")
            return result

        result["commit_hash"] = commit_result.get("commit_hash")
        result["commit_message"] = commit_msg

    # Step 7: ビルド実行（Electronアプリ等）
    if not skip_build:
        build_result = _execute_build(project_id, order_ids)
        result["steps"]["build"] = build_result

        # ビルド失敗は警告のみ（リリースは継続）
        if not build_result.get("success") and not build_result.get("skipped"):
            result["warnings"] = result.get("warnings", [])
            result["warnings"].append(f"Build failed: {build_result.get('error', 'unknown')}")

    return result


# ============================================================================
# 出力フォーマット
# ============================================================================

def format_output(result: Dict[str, Any], json_output: bool = False) -> str:
    """結果をフォーマット"""
    if json_output:
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    if not result.get("success"):
        return f"Error: {result.get('error', 'unknown error')}"

    lines = []

    if result.get("dry_run"):
        lines.append("=== DRY RUN (no changes) ===")
        lines.append("")

        # マイグレーションプレビュー
        migration_preview = result.get("steps", {}).get("migration_preview", {})
        if migration_preview.get("has_migrations"):
            lines.append("Migrations to execute:")
            for script in migration_preview.get("migration_scripts", []):
                lines.append(f"  * {script}")
            lines.append("")

        staging = result.get("steps", {}).get("staging_preview", {})
        files = staging.get("files", [])
        excluded = staging.get("excluded", [])

        lines.append(f"Staging target: {len(files)} files (excluded: {len(excluded)})")
        for f in files[:30]:
            lines.append(f"  + {f}")
        if len(files) > 30:
            lines.append(f"  ... and {len(files) - 30} more")

        if excluded:
            lines.append("")
            lines.append(f"Excluded ({len(excluded)}):")
            for f in excluded[:10]:
                lines.append(f"  - {f}")
            if len(excluded) > 10:
                lines.append(f"  ... and {len(excluded) - 10} more")

        lines.append("")
        lines.append("Commit message:")
        lines.append(result.get("steps", {}).get("commit_message_preview", ""))
    else:
        lines.append(f"Release completed for {', '.join(result['order_ids'])}")

        if result.get("commit_hash"):
            lines.append(f"  Commit: {result['commit_hash']}")

        steps = result.get("steps", {})

        # マイグレーション実行結果
        migrations = steps.get("migrations", {})
        if migrations.get("executed"):
            lines.append(f"  Migrations executed: {len(migrations['executed'])}")
            for mig in migrations["executed"]:
                status = "[OK]" if mig.get("success") else "[FAILED]"
                lines.append(f"    {status} {Path(mig['script']).name}")

        if steps.get("complete_orders"):
            lines.append(f"  Orders completed: {', '.join(steps['complete_orders'])}")

        bl_updates = steps.get("backlog_updates", [])
        if bl_updates:
            lines.append(f"  Backlogs updated: {', '.join(bl['id'] for bl in bl_updates)}")

        staging = steps.get("staging", {})
        if staging.get("files"):
            lines.append(f"  Files committed: {len(staging['files'])}")

        # ビルド実行結果
        build = steps.get("build", {})
        if build.get("success") and not build.get("skipped"):
            lines.append(f"  Build: SUCCESS (Build ID: {build.get('build_id')})")
            if build.get("artifact_path"):
                lines.append(f"    Artifact: {build['artifact_path']}")
        elif not build.get("success") and not build.get("skipped"):
            lines.append(f"  Build: FAILED - {build.get('error', 'unknown')}")

        # 警告表示
        warnings = result.get("warnings", [])
        if warnings:
            lines.append("")
            lines.append("Warnings:")
            for warn in warnings:
                lines.append(f"  ! {warn}")

    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="AI PM Framework - 統合リリース (ORDER完了 + BACKLOG + RELEASE_LOG + git commit)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", nargs="?", help="ORDER ID")
    parser.add_argument("--multi", help="複数ORDER (カンマ区切り: ORDER_099,ORDER_100)")
    parser.add_argument("--dry-run", action="store_true", help="変更を行わない")
    parser.add_argument("--skip-complete", action="store_true")
    parser.add_argument("--skip-backlog", action="store_true")
    parser.add_argument("--skip-log", action="store_true")
    parser.add_argument("--skip-git", action="store_true")
    parser.add_argument("--skip-migration", action="store_true", help="マイグレーション実行をスキップ")
    parser.add_argument("--skip-build", action="store_true", help="ビルド実行をスキップ")
    parser.add_argument("--extra-files", help="追加ステージング対象 (カンマ区切り)")
    parser.add_argument("--message", help="カスタムコミットメッセージ")
    parser.add_argument("--json", action="store_true", help="JSON出力")

    args = parser.parse_args()

    # ORDER ID解決
    if args.multi:
        order_ids = [oid.strip() for oid in args.multi.split(",")]
    elif args.order_id:
        order_ids = [args.order_id]
    else:
        parser.error("ORDER_ID or --multi required")
        return

    extra_files = None
    if args.extra_files:
        extra_files = [f.strip() for f in args.extra_files.split(",")]

    try:
        result = execute_git_release(
            project_id=args.project_id,
            order_ids=order_ids,
            dry_run=args.dry_run,
            skip_complete=args.skip_complete,
            skip_backlog=args.skip_backlog,
            skip_log=args.skip_log,
            skip_git=args.skip_git,
            skip_migration=args.skip_migration,
            skip_build=args.skip_build,
            extra_files=extra_files,
            custom_message=args.message,
        )

        print(format_output(result, json_output=args.json))
        sys.exit(0 if result.get("success") else 1)

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)},
                             ensure_ascii=False))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
