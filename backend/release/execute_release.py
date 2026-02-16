#!/usr/bin/env python3
"""
AI PM Framework - マイグレーション→ビルド→デプロイ 一括実行オーケストレーター

破壊的DB変更を含むORDERのリリース時に、以下のフローを一括実行する:
  1. 破壊的DB変更タスクの検出（is_destructive_db_change = 1）
  2. マイグレーションスクリプト実行（ARTIFACTS/migrate/*.py）
  3. Electronアプリ等のビルド実行（build_manager.py経由）
  4. デプロイ（成果物の検証）

git_release.py から呼び出されるほか、CLIとしても単体実行可能。

Usage:
    # マイグレーション→ビルド→デプロイ一括実行
    python release/execute_release.py PROJECT_ID ORDER_ID [OPTIONS]

    # マイグレーションのみ実行
    python release/execute_release.py PROJECT_ID ORDER_ID --migration-only

    # ビルドのみ実行
    python release/execute_release.py PROJECT_ID ORDER_ID --build-only

    # ドライラン
    python release/execute_release.py PROJECT_ID ORDER_ID --dry-run

Options:
    --dry-run          変更を行わない（確認のみ）
    --migration-only   マイグレーションのみ実行
    --build-only       ビルドのみ実行
    --skip-migration   マイグレーションをスキップ
    --skip-build       ビルドをスキップ
    --force            Worker実行中でも強制実行
    --json             JSON出力
    --verbose          詳細ログ出力
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 親パッケージからインポート
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import setup_utf8_output
from utils.db import get_connection, fetch_all, fetch_one

setup_utf8_output()


# ============================================================================
# マイグレーション検出
# ============================================================================

def detect_migrations(
    project_id: str,
    order_ids: List[str],
    ai_pm_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    破壊的DB変更を含むタスクとマイグレーションスクリプトを検出

    Args:
        project_id: プロジェクトID
        order_ids: ORDER IDリスト
        ai_pm_root: AI PMルートディレクトリ

    Returns:
        {
            "has_migrations": bool,
            "migration_tasks": [...],
            "migration_scripts": [...],
        }
    """
    if ai_pm_root is None:
        ai_pm_root = Path(__file__).resolve().parent.parent.parent

    conn = get_connection()
    result = {
        "has_migrations": False,
        "migration_tasks": [],
        "migration_scripts": [],
    }

    for order_id in order_ids:
        tasks = fetch_all(
            conn,
            """SELECT id, title, description, is_destructive_db_change
               FROM tasks
               WHERE order_id = ? AND project_id = ?
               AND is_destructive_db_change = 1""",
            (order_id, project_id),
        )

        for task in tasks:
            task_dict = dict(task)
            result["migration_tasks"].append(task_dict)
            result["has_migrations"] = True

        # ARTIFACTS配下のマイグレーションスクリプトを検出
        artifacts_path = (
            ai_pm_root / "PROJECTS" / project_id / "RESULT" / order_id / "06_ARTIFACTS"
        )

        if artifacts_path.exists():
            for script in sorted(artifacts_path.rglob("migrate/*.py")):
                if script.name != "__init__.py":
                    result["migration_scripts"].append(str(script))

    conn.close()
    return result


# ============================================================================
# マイグレーション実行
# ============================================================================

def execute_migrations(
    project_id: str,
    order_ids: List[str],
    ai_pm_root: Optional[Path] = None,
    *,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    マイグレーションスクリプトを実行

    MigrationRunnerを内部的に使用し、以下の安全機構を提供:
    - 自動バックアップ作成
    - PRAGMA foreign_keys制御
    - Worker実行中の検出・警告
    - トランザクション管理

    Args:
        project_id: プロジェクトID
        order_ids: ORDER IDリスト
        ai_pm_root: AI PMルートディレクトリ
        dry_run: ドライランモード
        force: Worker実行中でも強制実行
        verbose: 詳細ログ出力

    Returns:
        実行結果辞書
    """
    if ai_pm_root is None:
        ai_pm_root = Path(__file__).resolve().parent.parent.parent

    result: Dict[str, Any] = {
        "success": True,
        "executed": [],
        "skipped": [],
        "dry_run": dry_run,
    }

    # 破壊的DB変更タスクの検出
    detection = detect_migrations(project_id, order_ids, ai_pm_root)

    if not detection["has_migrations"]:
        result["skipped"].append("No destructive DB change tasks found")
        return result

    if not detection["migration_scripts"]:
        result["skipped"].append(
            "Destructive DB change tasks found but no migration scripts in ARTIFACTS"
        )
        result["migration_tasks"] = detection["migration_tasks"]
        return result

    if verbose:
        print(f"[INFO] Detected {len(detection['migration_scripts'])} migration script(s)")
        for script in detection["migration_scripts"]:
            print(f"  - {Path(script).name}")

    # Worker実行中チェック（MigrationRunnerに任せるが、事前にも確認）
    if not force and not dry_run:
        try:
            from utils.migration_base import check_worker_safety
            safety = check_worker_safety(verbose=verbose)
            if not safety["safe"]:
                result["success"] = False
                result["error"] = (
                    f"Worker safety check failed: {safety['warning']} "
                    "Use --force to override."
                )
                result["running_tasks"] = safety["running_tasks"]
                return result
        except ImportError:
            pass  # migration_baseが使えない場合はスキップ

    # マイグレーションスクリプトを順次実行
    for script_path in detection["migration_scripts"]:
        script_name = Path(script_path).name

        if verbose:
            print(f"[INFO] Executing migration: {script_name}")

        # CLIオプション構築
        cmd = [sys.executable, script_path, "--verbose"]
        if dry_run:
            cmd.append("--dry-run")
        if force:
            cmd.append("--force")

        try:
            run_result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(ai_pm_root),
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )

            entry = {
                "script": script_path,
                "script_name": script_name,
                "success": run_result.returncode == 0,
                "output": run_result.stdout[:500] if run_result.stdout else "",
            }

            if run_result.returncode == 0:
                if verbose:
                    print(f"[INFO] Migration succeeded: {script_name}")
                result["executed"].append(entry)
            else:
                entry["error"] = run_result.stderr[:500] if run_result.stderr else ""
                result["executed"].append(entry)
                result["success"] = False
                result["error"] = f"Migration failed: {script_name}"
                if verbose:
                    print(f"[ERROR] Migration failed: {script_name}")
                    print(f"  stderr: {run_result.stderr[:200]}")
                return result  # 最初の失敗で中断

        except subprocess.TimeoutExpired:
            result["success"] = False
            result["error"] = f"Migration timeout (120s): {script_name}"
            result["executed"].append({
                "script": script_path,
                "script_name": script_name,
                "success": False,
                "error": "Timeout after 120 seconds",
            })
            return result

        except Exception as e:
            result["success"] = False
            result["error"] = f"Migration execution error: {e}"
            return result

    return result


# ============================================================================
# ビルド実行
# ============================================================================

def execute_build_step(
    project_id: str,
    order_ids: List[str],
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    ビルドを実行（プロジェクトにビルド設定がある場合のみ）

    build_manager.pyを使用してElectronアプリ等をビルドする。
    ビルド設定はBUILD_CONFIGSに定義されたプロジェクトのみ対象。

    Args:
        project_id: プロジェクトID
        order_ids: ORDER IDリスト
        dry_run: ドライランモード
        verbose: 詳細ログ出力

    Returns:
        ビルド結果辞書
    """
    result: Dict[str, Any] = {
        "success": True,
        "skipped": False,
    }

    try:
        from release.build_manager import execute_build, BUILD_CONFIGS

        if project_id not in BUILD_CONFIGS:
            result["skipped"] = True
            result["message"] = f"No build config for project: {project_id}"
            if verbose:
                print(f"[INFO] Build skipped: {result['message']}")
            return result

        order_id = order_ids[-1] if order_ids else None

        if verbose:
            config = BUILD_CONFIGS[project_id]
            print(f"[INFO] Starting build for {project_id}")
            print(f"  Build dir: {config['build_dir']}")
            print(f"  Pre-build: {config.get('pre_build', 'none')}")
            print(f"  Build command: {config['build_command']}")

        build_result = execute_build(
            project_id=project_id,
            order_id=order_id,
            dry_run=dry_run,
        )

        if not build_result.get("success"):
            result["success"] = False
            result["error"] = build_result.get("error", "Build failed")
            if verbose:
                print(f"[ERROR] Build failed: {result['error']}")
            return result

        result["build_id"] = build_result.get("build_id")
        result["artifact_path"] = build_result.get("artifact_path")
        result["dry_run"] = build_result.get("dry_run", False)

        if verbose:
            if dry_run:
                print("[INFO] Build dry run completed")
            else:
                print(f"[INFO] Build succeeded (ID: {result.get('build_id')})")
                if result.get("artifact_path"):
                    print(f"  Artifact: {result['artifact_path']}")

    except ImportError:
        result["skipped"] = True
        result["message"] = "build_manager not available"
        if verbose:
            print(f"[INFO] Build skipped: {result['message']}")

    except Exception as e:
        result["success"] = False
        result["error"] = str(e)
        if verbose:
            print(f"[ERROR] Build error: {e}")

    return result


# ============================================================================
# デプロイ検証
# ============================================================================

def verify_deploy(
    project_id: str,
    build_result: Dict[str, Any],
    *,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    デプロイ（成果物の存在と整合性）を検証

    Args:
        project_id: プロジェクトID
        build_result: ビルド結果
        verbose: 詳細ログ出力

    Returns:
        デプロイ検証結果
    """
    result: Dict[str, Any] = {
        "success": True,
        "verified": False,
    }

    # ビルドがスキップされた場合は検証不要
    if build_result.get("skipped"):
        result["message"] = "Build was skipped, no deploy verification needed"
        return result

    # ビルドが失敗した場合は検証不可
    if not build_result.get("success"):
        result["success"] = False
        result["error"] = "Cannot verify deploy: build failed"
        return result

    # ドライランの場合
    if build_result.get("dry_run"):
        result["message"] = "Dry run: deploy verification skipped"
        return result

    # 成果物の存在確認
    artifact_path = build_result.get("artifact_path")
    if artifact_path:
        artifact = Path(artifact_path)
        if artifact.exists():
            result["verified"] = True
            result["artifact_path"] = str(artifact)
            result["artifact_size"] = artifact.stat().st_size
            if verbose:
                size_mb = result["artifact_size"] / (1024 * 1024)
                print(f"[INFO] Deploy verified: {artifact_path} ({size_mb:.1f} MB)")
        else:
            result["success"] = False
            result["error"] = f"Artifact not found: {artifact_path}"
            if verbose:
                print(f"[ERROR] {result['error']}")
    else:
        result["message"] = "No artifact path to verify"

    return result


# ============================================================================
# 統合フロー: マイグレーション→ビルド→デプロイ
# ============================================================================

def execute_migration_build_deploy(
    project_id: str,
    order_ids: List[str],
    *,
    dry_run: bool = False,
    skip_migration: bool = False,
    skip_build: bool = False,
    force: bool = False,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    マイグレーション→ビルド→デプロイの一括実行フロー

    破壊的DB変更を含むORDERのリリース時に使用する。
    git_release.py から呼び出されるメインAPIメソッド。

    実行順序:
      1. マイグレーションスクリプト検出・実行
      2. ビルド実行（Electronアプリ等）
      3. デプロイ検証（成果物確認）

    Args:
        project_id: プロジェクトID
        order_ids: ORDER IDリスト
        dry_run: ドライランモード
        skip_migration: マイグレーションをスキップ
        skip_build: ビルドをスキップ
        force: Worker実行中でも強制実行
        verbose: 詳細ログ出力

    Returns:
        統合実行結果辞書
    """
    ai_pm_root = Path(__file__).resolve().parent.parent.parent

    result: Dict[str, Any] = {
        "success": True,
        "project_id": project_id,
        "order_ids": order_ids,
        "dry_run": dry_run,
        "steps": {},
        "executed_at": datetime.now().isoformat(),
    }

    if verbose:
        mode = "DRY RUN" if dry_run else "LIVE"
        print(f"[INFO] === Migration→Build→Deploy ({mode}) ===")
        print(f"[INFO] Project: {project_id}")
        print(f"[INFO] Orders: {', '.join(order_ids)}")

    # Step 1: マイグレーション
    if not skip_migration:
        if verbose:
            print("\n[INFO] --- Step 1: Migration ---")

        migration_result = execute_migrations(
            project_id=project_id,
            order_ids=order_ids,
            ai_pm_root=ai_pm_root,
            dry_run=dry_run,
            force=force,
            verbose=verbose,
        )
        result["steps"]["migration"] = migration_result

        if not migration_result["success"]:
            result["success"] = False
            result["error"] = migration_result.get("error", "Migration failed")
            if verbose:
                print(f"\n[ERROR] Migration failed - aborting release")
            return result
    else:
        result["steps"]["migration"] = {"skipped": True, "message": "Migration skipped by user"}
        if verbose:
            print("\n[INFO] --- Step 1: Migration (SKIPPED) ---")

    # Step 2: ビルド
    if not skip_build:
        if verbose:
            print("\n[INFO] --- Step 2: Build ---")

        build_result = execute_build_step(
            project_id=project_id,
            order_ids=order_ids,
            dry_run=dry_run,
            verbose=verbose,
        )
        result["steps"]["build"] = build_result

        # ビルド失敗は警告のみ（リリースは継続）
        if not build_result.get("success") and not build_result.get("skipped"):
            result["warnings"] = result.get("warnings", [])
            result["warnings"].append(
                f"Build failed: {build_result.get('error', 'unknown')}"
            )
            if verbose:
                print(f"[WARNING] Build failed but continuing release")
    else:
        build_result = {"skipped": True, "message": "Build skipped by user"}
        result["steps"]["build"] = build_result
        if verbose:
            print("\n[INFO] --- Step 2: Build (SKIPPED) ---")

    # Step 3: デプロイ検証
    if verbose:
        print("\n[INFO] --- Step 3: Deploy Verification ---")

    deploy_result = verify_deploy(
        project_id=project_id,
        build_result=build_result,
        verbose=verbose,
    )
    result["steps"]["deploy"] = deploy_result

    if verbose:
        status = "SUCCESS" if result["success"] else "FAILED"
        warnings = result.get("warnings", [])
        print(f"\n[INFO] === Result: {status} ===")
        if warnings:
            for w in warnings:
                print(f"[WARNING] {w}")

    return result


# ============================================================================
# 出力フォーマット
# ============================================================================

def format_output(result: Dict[str, Any], json_output: bool = False) -> str:
    """結果をフォーマットして文字列で返す"""
    if json_output:
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    lines = []
    steps = result.get("steps", {})
    is_dry_run = result.get("dry_run", False)

    if is_dry_run:
        lines.append("=== Migration→Build→Deploy (DRY RUN) ===")
    else:
        lines.append("=== Migration→Build→Deploy ===")

    lines.append(f"  Project: {result.get('project_id', '?')}")
    lines.append(f"  Orders: {', '.join(result.get('order_ids', []))}")
    lines.append("")

    # マイグレーション結果
    migration = steps.get("migration", {})
    if migration.get("skipped") is True:
        lines.append("[Migration] SKIPPED")
    elif migration.get("executed"):
        lines.append(f"[Migration] Executed: {len(migration['executed'])} script(s)")
        for mig in migration["executed"]:
            status = "OK" if mig.get("success") else "FAILED"
            lines.append(f"  [{status}] {mig.get('script_name', Path(mig['script']).name)}")
    elif migration.get("skipped"):
        for msg in migration.get("skipped", []):
            lines.append(f"[Migration] {msg}")
    lines.append("")

    # ビルド結果
    build = steps.get("build", {})
    if build.get("skipped"):
        lines.append(f"[Build] SKIPPED - {build.get('message', '')}")
    elif build.get("success"):
        if build.get("dry_run"):
            lines.append("[Build] DRY RUN - OK")
        else:
            lines.append(f"[Build] SUCCESS (ID: {build.get('build_id', '?')})")
            if build.get("artifact_path"):
                lines.append(f"  Artifact: {build['artifact_path']}")
    else:
        lines.append(f"[Build] FAILED - {build.get('error', 'unknown')}")
    lines.append("")

    # デプロイ結果
    deploy = steps.get("deploy", {})
    if deploy.get("verified"):
        size_mb = deploy.get("artifact_size", 0) / (1024 * 1024)
        lines.append(f"[Deploy] VERIFIED ({size_mb:.1f} MB)")
    elif deploy.get("message"):
        lines.append(f"[Deploy] {deploy['message']}")
    elif not deploy.get("success"):
        lines.append(f"[Deploy] FAILED - {deploy.get('error', 'unknown')}")
    lines.append("")

    # 全体結果
    if not result.get("success"):
        lines.append(f"Result: FAILED - {result.get('error', '')}")
    else:
        lines.append("Result: SUCCESS")

    # 警告
    warnings = result.get("warnings", [])
    if warnings:
        lines.append("")
        lines.append("Warnings:")
        for w in warnings:
            lines.append(f"  ! {w}")

    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="AI PM Framework - マイグレーション→ビルド→デプロイ一括実行",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("project_id", help="プロジェクトID")
    parser.add_argument("order_id", nargs="?", help="ORDER ID")
    parser.add_argument("--multi", help="複数ORDER (カンマ区切り)")
    parser.add_argument("--dry-run", action="store_true", help="変更を行わない")
    parser.add_argument("--migration-only", action="store_true",
                        help="マイグレーションのみ実行")
    parser.add_argument("--build-only", action="store_true",
                        help="ビルドのみ実行")
    parser.add_argument("--skip-migration", action="store_true",
                        help="マイグレーションをスキップ")
    parser.add_argument("--skip-build", action="store_true",
                        help="ビルドをスキップ")
    parser.add_argument("--force", action="store_true",
                        help="Worker実行中でも強制実行")
    parser.add_argument("--json", action="store_true", help="JSON出力")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="詳細ログ出力")

    args = parser.parse_args()

    # ORDER ID解決
    if args.multi:
        order_ids = [oid.strip() for oid in args.multi.split(",")]
    elif args.order_id:
        order_ids = [args.order_id]
    else:
        parser.error("ORDER_ID or --multi required")
        return

    # --migration-only / --build-only の処理
    skip_migration = args.skip_migration
    skip_build = args.skip_build

    if args.migration_only:
        skip_build = True
    if args.build_only:
        skip_migration = True

    try:
        result = execute_migration_build_deploy(
            project_id=args.project_id,
            order_ids=order_ids,
            dry_run=args.dry_run,
            skip_migration=skip_migration,
            skip_build=skip_build,
            force=args.force,
            verbose=args.verbose,
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
