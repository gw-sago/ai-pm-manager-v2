#!/usr/bin/env python3
"""
AI PM Framework - ビルドステータス管理

Electronアプリ等のビルド実行とステータスをDBで追跡する。

Usage:
    # ビルド実行
    python backend/release/build_manager.py PROJECT_ID --order ORDER_ID

    # ビルド履歴表示
    python backend/release/build_manager.py PROJECT_ID --status [--json]

    # ドライラン
    python backend/release/build_manager.py PROJECT_ID --order ORDER_ID --dry-run
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import setup_utf8_output
from utils.db import get_connection, fetch_all, fetch_one

setup_utf8_output()

# ============================================================================
# プロジェクト別ビルド設定
# ============================================================================

BUILD_CONFIGS: Dict[str, Dict[str, Any]] = {
    "ai_pm_manager": {
        "build_dir": "D:/your_workspace/ai-pm-manager-v2",
        "pre_build": "npx tsc --noEmit",
        "build_command": "npx electron-forge package",
        "artifact_path": "out/ai-pm-manager-v2-win32-x64/ai-pm-manager-v2.exe",
        "build_type": "electron",
    },
}


# ============================================================================
# ビルドDB操作
# ============================================================================

def _create_build_record(
    project_id: str,
    order_id: Optional[str] = None,
    release_id: Optional[str] = None,
    build_type: str = "electron",
    build_command: Optional[str] = None,
) -> int:
    """builds テーブルにPENDINGレコードを挿入"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO builds
           (project_id, order_id, release_id, build_type, status, build_command)
           VALUES (?, ?, ?, ?, 'PENDING', ?)""",
        (project_id, order_id, release_id, build_type, build_command),
    )
    build_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return build_id


def _update_build_status(
    build_id: int,
    status: str,
    build_output: Optional[str] = None,
    artifact_path: Optional[str] = None,
) -> None:
    """ビルドステータスを更新"""
    conn = get_connection()

    now_field = "started_at" if status == "BUILDING" else "completed_at"
    params = [status]
    set_parts = [f"status = ?"]

    if status == "BUILDING":
        set_parts.append("started_at = datetime('now')")
    elif status in ("SUCCESS", "FAILED"):
        set_parts.append("completed_at = datetime('now')")

    if build_output is not None:
        set_parts.append("build_output = ?")
        # 出力を最大4000文字に制限
        params.append(build_output[:4000])

    if artifact_path is not None:
        set_parts.append("artifact_path = ?")
        params.append(artifact_path)

    params.append(build_id)
    conn.execute(
        f"UPDATE builds SET {', '.join(set_parts)} WHERE id = ?",
        params,
    )
    conn.commit()
    conn.close()


def get_build_history(
    project_id: str,
    limit: int = 10,
) -> list:
    """ビルド履歴を取得"""
    conn = get_connection()
    rows = fetch_all(
        conn,
        """SELECT id, project_id, order_id, release_id, build_type,
                  status, build_command, artifact_path,
                  started_at, completed_at, created_at
           FROM builds
           WHERE project_id = ?
           ORDER BY created_at DESC
           LIMIT ?""",
        (project_id, limit),
    )
    conn.close()
    return [dict(r) for r in rows]


# ============================================================================
# ビルド実行
# ============================================================================

def _run_command(cmd: str, cwd: str, timeout: int = 300) -> Dict[str, Any]:
    """コマンドを実行して結果を返す"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
        }


def execute_build(
    project_id: str,
    order_id: Optional[str] = None,
    release_id: Optional[str] = None,
    build_dir: Optional[str] = None,
    timeout: int = 300,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    ビルドを実行しステータスをDBに記録

    Returns:
        実行結果の辞書
    """
    config = BUILD_CONFIGS.get(project_id)
    if not config:
        return {
            "success": False,
            "error": f"No build config for project: {project_id}",
            "available_projects": list(BUILD_CONFIGS.keys()),
        }

    actual_build_dir = build_dir or config["build_dir"]
    build_path = Path(actual_build_dir)

    if not build_path.exists():
        return {
            "success": False,
            "error": f"Build directory not found: {actual_build_dir}",
        }

    build_type = config["build_type"]
    build_command = config["build_command"]

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "project_id": project_id,
            "order_id": order_id,
            "build_dir": str(build_path),
            "pre_build": config.get("pre_build"),
            "build_command": build_command,
            "artifact_check": config.get("artifact_path"),
            "message": "Dry run: no build executed",
        }

    # DB: PENDING レコード作成
    build_id = _create_build_record(
        project_id=project_id,
        order_id=order_id,
        release_id=release_id,
        build_type=build_type,
        build_command=build_command,
    )

    result: Dict[str, Any] = {
        "build_id": build_id,
        "project_id": project_id,
        "order_id": order_id,
        "build_dir": str(build_path),
    }

    # DB: BUILDING に更新
    _update_build_status(build_id, "BUILDING")

    # Pre-build (型チェック等)
    pre_build_cmd = config.get("pre_build")
    if pre_build_cmd:
        pre_result = _run_command(pre_build_cmd, str(build_path), timeout)
        result["pre_build"] = {
            "command": pre_build_cmd,
            "success": pre_result["success"],
        }
        if not pre_result["success"]:
            output = pre_result["stderr"] or pre_result["stdout"]
            _update_build_status(build_id, "FAILED",
                                 build_output=f"Pre-build failed: {output}")
            result["success"] = False
            result["error"] = f"Pre-build failed: {output[:200]}"
            return result

    # Build実行
    build_result = _run_command(build_command, str(build_path), timeout)
    result["build"] = {
        "command": build_command,
        "success": build_result["success"],
    }

    if not build_result["success"]:
        output = build_result["stderr"] or build_result["stdout"]
        _update_build_status(build_id, "FAILED",
                             build_output=f"Build failed: {output}")
        result["success"] = False
        result["error"] = f"Build failed: {output[:200]}"
        return result

    # Artifact確認
    artifact_rel = config.get("artifact_path")
    artifact_full = None
    if artifact_rel:
        artifact_full = str(build_path / artifact_rel)
        if not Path(artifact_full).exists():
            _update_build_status(
                build_id, "FAILED",
                build_output=f"Artifact not found: {artifact_full}",
            )
            result["success"] = False
            result["error"] = f"Artifact not found: {artifact_full}"
            return result

    # SUCCESS
    _update_build_status(
        build_id, "SUCCESS",
        build_output=build_result["stdout"][:2000],
        artifact_path=artifact_full,
    )

    result["success"] = True
    result["status"] = "SUCCESS"
    result["artifact_path"] = artifact_full
    return result


# ============================================================================
# 出力フォーマット
# ============================================================================

def format_output(result: Dict[str, Any], json_output: bool = False) -> str:
    if json_output:
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    if "builds" in result:
        # 履歴表示
        lines = [f"Build history for {result.get('project_id', '?')}:", ""]
        for b in result["builds"]:
            status_mark = {"SUCCESS": "[OK]", "FAILED": "[NG]", "BUILDING": "[..]",
                           "PENDING": "[--]", "SKIPPED": "[SK]"}.get(b["status"], "[??]")
            lines.append(
                f"  {status_mark} #{b['id']} {b.get('order_id', '-'):12s} "
                f"{b['status']:10s} {b.get('created_at', '')}"
            )
        if not result["builds"]:
            lines.append("  (no builds)")
        return "\n".join(lines)

    if not result.get("success"):
        return f"Build error: {result.get('error', 'unknown')}"

    if result.get("dry_run"):
        lines = [
            "=== BUILD DRY RUN ===",
            f"  Project:  {result['project_id']}",
            f"  Order:    {result.get('order_id', '-')}",
            f"  Dir:      {result['build_dir']}",
            f"  Pre-build: {result.get('pre_build', '-')}",
            f"  Build:    {result['build_command']}",
            f"  Artifact: {result.get('artifact_check', '-')}",
        ]
        return "\n".join(lines)

    lines = [
        f"Build #{result.get('build_id', '?')} - {result.get('status', 'UNKNOWN')}",
        f"  Project: {result['project_id']}",
    ]
    if result.get("artifact_path"):
        lines.append(f"  Artifact: {result['artifact_path']}")
    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="AI PM Framework - ビルドステータス管理",
    )
    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("--order", help="関連ORDER ID")
    parser.add_argument("--release-id", help="関連リリースID")
    parser.add_argument("--type", default="electron", help="ビルド種別")
    parser.add_argument("--build-dir", help="ビルド実行ディレクトリ（上書き）")
    parser.add_argument("--timeout", type=int, default=300, help="タイムアウト秒")
    parser.add_argument("--status", action="store_true", help="ビルド履歴表示")
    parser.add_argument("--limit", type=int, default=10, help="履歴件数")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    try:
        if args.status:
            builds = get_build_history(args.project_id, args.limit)
            output = format_output(
                {"project_id": args.project_id, "builds": builds},
                json_output=args.json,
            )
        else:
            result = execute_build(
                project_id=args.project_id,
                order_id=args.order,
                release_id=args.release_id,
                build_dir=args.build_dir,
                timeout=args.timeout,
                dry_run=args.dry_run,
            )
            output = format_output(result, json_output=args.json)

        print(output)
        sys.exit(0)

    except Exception as e:
        if args.json:
            print(json.dumps({"success": False, "error": str(e)},
                             ensure_ascii=False))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
