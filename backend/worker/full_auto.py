#!/usr/bin/env python3
"""
AI PM Framework - フルオート ORDER 実行スクリプト

ORDER_062: フルオートORDER実行
PM処理 → Worker処理（並列対応）→ レビュー処理 のサイクルを全自動で実行する。

Usage:
    python backend/worker/full_auto.py PROJECT_NAME ORDER_ID [options]

Options:
    --max-cycles N      最大サイクル数（デフォルト: 50）
    --timeout SEC       タスクごとのタイムアウト秒数（デフォルト: 1800）
    --model MODEL       AIモデル（haiku/sonnet/opus、デフォルト: sonnet）
    --verbose           詳細ログ出力
    --json              JSON形式で出力
    --dry-run           実行計画のみ表示（実際の処理は行わない）

Example:
    python backend/worker/full_auto.py ai_pm_manager_v2 ORDER_062
    python backend/worker/full_auto.py ai_pm_manager_v2 ORDER_062 --model opus --verbose
    python backend/worker/full_auto.py ai_pm_manager_v2 ORDER_062 --dry-run
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 内部モジュールインポート
try:
    from utils.db import (
        get_connection, fetch_one, fetch_all,
        row_to_dict, rows_to_dicts, DatabaseError
    )
    from utils.validation import (
        validate_project_name, project_exists, ValidationError
    )
    from config.db_config import get_project_paths
except ImportError as e:
    logger.error(f"内部モジュールのインポートに失敗: {e}")
    sys.exit(1)


def get_order_status(project_name: str, order_id: str) -> Optional[Dict[str, Any]]:
    """ORDERのステータスを取得する"""
    try:
        with get_connection() as conn:
            row = fetch_one(
                conn,
                "SELECT id, status, title FROM orders WHERE project_name = ? AND order_id = ?",
                (project_name, order_id)
            )
            if row:
                return row_to_dict(row)
            return None
    except DatabaseError as e:
        logger.error(f"ORDER取得エラー: {e}")
        return None


def get_queued_tasks(project_name: str, order_id: str) -> List[Dict[str, Any]]:
    """QUEUEDタスクの一覧を取得する"""
    try:
        with get_connection() as conn:
            rows = fetch_all(
                conn,
                """SELECT task_id, title, status, priority, assigned_model
                   FROM tasks
                   WHERE project_name = ? AND order_id = ?
                     AND status IN ('QUEUED', 'IN_PROGRESS', 'REWORK')
                   ORDER BY priority ASC, task_id ASC""",
                (project_name, order_id)
            )
            return rows_to_dicts(rows)
    except DatabaseError as e:
        logger.error(f"タスク取得エラー: {e}")
        return []


def get_all_tasks(project_name: str, order_id: str) -> List[Dict[str, Any]]:
    """全タスクの一覧を取得する"""
    try:
        with get_connection() as conn:
            rows = fetch_all(
                conn,
                """SELECT task_id, title, status, priority, assigned_model
                   FROM tasks
                   WHERE project_name = ? AND order_id = ?
                   ORDER BY priority ASC, task_id ASC""",
                (project_name, order_id)
            )
            return rows_to_dicts(rows)
    except DatabaseError as e:
        logger.error(f"タスク取得エラー: {e}")
        return []


def run_full_auto(
    project_name: str,
    order_id: str,
    max_cycles: int = 50,
    timeout_sec: int = 1800,
    model: str = 'sonnet',
    verbose: bool = False,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    フルオートORDER実行のメイン処理

    Args:
        project_name: プロジェクト名
        order_id: ORDER ID
        max_cycles: 最大サイクル数
        timeout_sec: タスクごとのタイムアウト秒数
        model: AIモデル
        verbose: 詳細ログ出力フラグ
        dry_run: ドライランフラグ

    Returns:
        実行結果辞書
    """
    started_at = datetime.now().isoformat()
    cycles_completed = 0
    stop_reason = 'unknown'
    tasks_completed = []
    tasks_failed = []

    logger.info(f"[FullAuto] 開始: {project_name}/{order_id}")
    logger.info(f"[FullAuto] 設定: max_cycles={max_cycles}, timeout={timeout_sec}s, model={model}")

    if dry_run:
        logger.info("[FullAuto] ドライランモード: 実際の処理は行いません")

    # ORDER存在確認
    order_info = get_order_status(project_name, order_id)
    if not order_info:
        return {
            'success': False,
            'error': f"ORDER not found: {project_name}/{order_id}",
            'cycles_completed': 0,
            'stop_reason': 'order_not_found',
            'tasks_completed': [],
            'tasks_failed': [],
            'started_at': started_at,
            'completed_at': datetime.now().isoformat(),
        }

    logger.info(f"[FullAuto] ORDER: {order_info.get('title', order_id)} (status={order_info.get('status')})")

    # プロジェクトパスを取得
    try:
        paths = get_project_paths(project_name)
        framework_path = str(Path(paths['base']).parent.parent)
    except Exception as e:
        logger.error(f"[FullAuto] プロジェクトパス取得エラー: {e}")
        framework_path = str(_project_root)

    if dry_run:
        # ドライラン: タスク一覧を表示して終了
        tasks = get_all_tasks(project_name, order_id)
        logger.info(f"[FullAuto] ドライラン完了: {len(tasks)} タスクが存在")
        for t in tasks:
            logger.info(f"  - {t.get('task_id')}: {t.get('title')} [{t.get('status')}]")
        return {
            'success': True,
            'dry_run': True,
            'tasks': tasks,
            'cycles_completed': 0,
            'stop_reason': 'dry_run',
            'tasks_completed': [],
            'tasks_failed': [],
            'started_at': started_at,
            'completed_at': datetime.now().isoformat(),
        }

    # メインサイクルループ
    import subprocess

    # parallel_launcher.py のパスを確認
    parallel_launcher_path = _package_root / 'worker' / 'parallel_launcher.py'
    execute_task_path = _package_root / 'worker' / 'execute_task.py'

    for cycle in range(1, max_cycles + 1):
        cycles_completed = cycle
        logger.info(f"[FullAuto] サイクル {cycle}/{max_cycles} 開始")

        # QUEUEDタスクを確認
        pending_tasks = get_queued_tasks(project_name, order_id)
        if not pending_tasks:
            logger.info("[FullAuto] 実行待ちタスクなし → 完了")
            stop_reason = 'all_tasks_completed'
            break

        logger.info(f"[FullAuto] 実行待ちタスク: {len(pending_tasks)} 件")
        for t in pending_tasks:
            logger.info(f"  - {t.get('task_id')}: {t.get('title')} [{t.get('status')}]")

        # parallel_launcher.py を使用（存在する場合）
        if parallel_launcher_path.exists():
            cmd = [
                sys.executable,
                str(parallel_launcher_path),
                project_name,
                order_id,
                '--timeout', str(timeout_sec),
                '--model', model,
            ]
            if verbose:
                cmd.append('--verbose')

            logger.info(f"[FullAuto] parallel_launcher.py 実行: {' '.join(cmd)}")
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=framework_path,
                    timeout=timeout_sec * len(pending_tasks) + 60,
                    capture_output=False,
                    text=True,
                    env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'}
                )
                exit_code = proc.returncode
                logger.info(f"[FullAuto] parallel_launcher.py 終了: exit_code={exit_code}")
                if exit_code != 0:
                    logger.warning(f"[FullAuto] parallel_launcher.py が非ゼロで終了: {exit_code}")
            except subprocess.TimeoutExpired:
                logger.error(f"[FullAuto] parallel_launcher.py タイムアウト")
                stop_reason = 'timeout'
                break
            except Exception as e:
                logger.error(f"[FullAuto] parallel_launcher.py 実行エラー: {e}")
                tasks_failed.append({'order_id': order_id, 'error': str(e)})
                stop_reason = 'error'
                break

        elif execute_task_path.exists():
            # フォールバック: 順次実行
            task = pending_tasks[0]
            task_id = task.get('task_id', '')
            cmd = [
                sys.executable,
                str(execute_task_path),
                project_name,
                task_id,
                '--timeout', str(timeout_sec),
                '--model', model,
                '--auto-review',
            ]
            if verbose:
                cmd.append('--verbose')

            logger.info(f"[FullAuto] execute_task.py 実行: {task_id}")
            try:
                proc = subprocess.run(
                    cmd,
                    cwd=framework_path,
                    timeout=timeout_sec + 60,
                    capture_output=False,
                    text=True,
                    env={**__import__('os').environ, 'PYTHONIOENCODING': 'utf-8'}
                )
                exit_code = proc.returncode
                if exit_code == 0:
                    tasks_completed.append(task_id)
                    logger.info(f"[FullAuto] タスク完了: {task_id}")
                else:
                    tasks_failed.append({'task_id': task_id, 'exit_code': exit_code})
                    logger.warning(f"[FullAuto] タスク失敗: {task_id} (exit_code={exit_code})")
            except subprocess.TimeoutExpired:
                logger.error(f"[FullAuto] タスクタイムアウト: {task_id}")
                tasks_failed.append({'task_id': task_id, 'error': 'timeout'})
                stop_reason = 'timeout'
                break
            except Exception as e:
                logger.error(f"[FullAuto] タスク実行エラー: {task_id}: {e}")
                tasks_failed.append({'task_id': task_id, 'error': str(e)})
                stop_reason = 'error'
                break
        else:
            logger.error("[FullAuto] 実行スクリプトが見つかりません")
            stop_reason = 'script_not_found'
            break

        # 残タスク確認
        remaining = get_queued_tasks(project_name, order_id)
        if not remaining:
            stop_reason = 'all_tasks_completed'
            logger.info("[FullAuto] 全タスク完了")
            break

    else:
        # max_cycles に達した
        stop_reason = 'max_cycles_reached'
        logger.warning(f"[FullAuto] 最大サイクル数 {max_cycles} に到達")

    completed_at = datetime.now().isoformat()
    success = stop_reason in ('all_tasks_completed',)

    result = {
        'success': success,
        'project_name': project_name,
        'order_id': order_id,
        'cycles_completed': cycles_completed,
        'stop_reason': stop_reason,
        'tasks_completed': tasks_completed,
        'tasks_failed': tasks_failed,
        'started_at': started_at,
        'completed_at': completed_at,
    }

    logger.info(f"[FullAuto] 完了: success={success}, stop_reason={stop_reason}, cycles={cycles_completed}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description='AI PM Framework - フルオートORDER実行',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('project_name', help='プロジェクト名')
    parser.add_argument('order_id', help='ORDER ID')
    parser.add_argument('--max-cycles', type=int, default=50, help='最大サイクル数（デフォルト: 50）')
    parser.add_argument('--timeout', type=int, default=1800, help='タスクごとのタイムアウト秒数（デフォルト: 1800）')
    parser.add_argument('--model', default='sonnet', choices=['haiku', 'sonnet', 'opus'], help='AIモデル')
    parser.add_argument('--verbose', action='store_true', help='詳細ログ出力')
    parser.add_argument('--json', action='store_true', dest='json_output', help='JSON形式で出力')
    parser.add_argument('--dry-run', action='store_true', help='実行計画のみ表示')

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        validate_project_name(args.project_name)
    except ValidationError as e:
        print(json.dumps({'success': False, 'error': str(e)}), flush=True)
        sys.exit(1)

    result = run_full_auto(
        project_name=args.project_name,
        order_id=args.order_id,
        max_cycles=args.max_cycles,
        timeout_sec=args.timeout,
        model=args.model,
        verbose=args.verbose,
        dry_run=args.dry_run
    )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False), flush=True)
    else:
        status = '成功' if result.get('success') else '失敗'
        print(f"\nフルオート実行結果: {status}")
        print(f"  サイクル数: {result.get('cycles_completed', 0)}")
        print(f"  停止理由: {result.get('stop_reason', 'unknown')}")
        if result.get('tasks_completed'):
            print(f"  完了タスク: {', '.join(result['tasks_completed'])}")
        if result.get('tasks_failed'):
            print(f"  失敗タスク: {result['tasks_failed']}")

    sys.exit(0 if result.get('success') else 1)


if __name__ == '__main__':
    main()
