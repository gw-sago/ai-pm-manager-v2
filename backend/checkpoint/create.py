#!/usr/bin/env python3
"""
AI PM Framework - Checkpoint作成モジュール

タスク実行前にDBスナップショットとファイル状態を保存します。

Usage:
    from checkpoint.create import create_checkpoint

    checkpoint_id = create_checkpoint(
        project_id="ai_pm_manager",
        task_id="TASK_932",
        order_id="ORDER_092"
    )
"""

import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

# パス設定
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent

if str(_package_root) not in sys.path:
    sys.path.insert(0, str(_package_root))

from utils.db import get_connection, DatabaseError
from config.db_config import USER_DATA_PATH, get_project_paths

logger = logging.getLogger(__name__)


class CheckpointError(Exception):
    """チェックポイント作成エラー"""
    pass


def create_checkpoint(
    project_id: str,
    task_id: str,
    order_id: Optional[str] = None,
    *,
    verbose: bool = False
) -> str:
    """
    チェックポイントを作成

    タスク実行前にDBスナップショットとファイル状態を保存します。

    Args:
        project_id: プロジェクトID
        task_id: タスクID
        order_id: ORDER ID（オプション）
        verbose: 詳細ログ出力

    Returns:
        チェックポイントID（タイムスタンプ形式）

    Raises:
        CheckpointError: チェックポイント作成失敗

    Example:
        checkpoint_id = create_checkpoint("ai_pm_manager", "TASK_932", "ORDER_092")
        # -> "20260209_102345_TASK_932"
    """
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # チェックポイントID生成（タイムスタンプ + タスクID）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    checkpoint_id = f"{timestamp}_{task_id}"

    logger.info(f"チェックポイント作成開始: {checkpoint_id}")

    try:
        # 1. DBスナップショット作成
        _create_db_snapshot(checkpoint_id, verbose)

        # 2. ファイル状態記録
        if order_id:
            _record_file_state(project_id, order_id, checkpoint_id, verbose)
        else:
            logger.info("ORDER ID未指定 - ファイル状態記録をスキップ")

        # 3. チェックポイントメタデータ保存
        _save_checkpoint_metadata(checkpoint_id, project_id, task_id, order_id, verbose)

        logger.info(f"チェックポイント作成完了: {checkpoint_id}")
        return checkpoint_id

    except Exception as e:
        logger.error(f"チェックポイント作成失敗: {e}")
        raise CheckpointError(f"チェックポイント作成失敗: {e}") from e


def _create_db_snapshot(checkpoint_id: str, verbose: bool = False) -> None:
    """
    DBスナップショットを作成

    data/aipm.db → data/checkpoints/{checkpoint_id}.db

    Args:
        checkpoint_id: チェックポイントID
        verbose: 詳細ログ出力

    Raises:
        CheckpointError: スナップショット作成失敗
    """
    # DB path（USER_DATA_PATH経由）
    db_path = USER_DATA_PATH / "data" / "aipm.db"
    checkpoint_dir = USER_DATA_PATH / "data" / "checkpoints"
    checkpoint_db_path = checkpoint_dir / f"{checkpoint_id}.db"

    if not db_path.exists():
        raise CheckpointError(f"DBファイルが見つかりません: {db_path}")

    # checkpointsディレクトリ作成
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    # DBファイルをコピー
    logger.debug(f"DBスナップショット作成: {db_path} -> {checkpoint_db_path}")
    shutil.copy2(db_path, checkpoint_db_path)

    # ファイルサイズ確認
    snapshot_size = checkpoint_db_path.stat().st_size
    logger.info(f"DBスナップショット作成完了: {checkpoint_db_path} ({snapshot_size:,} bytes)")


def _record_file_state(
    project_id: str,
    order_id: str,
    checkpoint_id: str,
    verbose: bool = False
) -> None:
    """
    ファイル状態を記録

    PROJECTS/{project}/RESULT/{order}/files_state.json を作成

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        checkpoint_id: チェックポイントID
        verbose: 詳細ログ出力

    Raises:
        CheckpointError: ファイル状態記録失敗
    """
    # RESULT directory（USER_DATA_PATH経由）
    result_dir = get_project_paths(project_id)["result"] / order_id

    if not result_dir.exists():
        logger.warning(f"RESULTディレクトリが見つかりません: {result_dir}")
        return

    # ファイル状態を収集
    file_states: List[Dict[str, Any]] = []

    for file_path in result_dir.rglob("*"):
        if file_path.is_file():
            # 除外パターン（.pyc, __pycache__, .gitなど）
            if any(x in str(file_path) for x in [".pyc", "__pycache__", ".git", ".DS_Store"]):
                continue

            relative_path = file_path.relative_to(result_dir)
            stat = file_path.stat()

            file_states.append({
                "path": str(relative_path),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "mtime_iso": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            })

    # files_state.json 保存
    state_file = result_dir / f"files_state_{checkpoint_id}.json"
    state_data = {
        "checkpoint_id": checkpoint_id,
        "project_id": project_id,
        "order_id": order_id,
        "created_at": datetime.now().isoformat(),
        "file_count": len(file_states),
        "files": file_states,
    }

    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f, ensure_ascii=False, indent=2)

    logger.info(f"ファイル状態記録完了: {state_file} ({len(file_states)} files)")


def _save_checkpoint_metadata(
    checkpoint_id: str,
    project_id: str,
    task_id: str,
    order_id: Optional[str],
    verbose: bool = False
) -> None:
    """
    チェックポイントメタデータを保存

    data/checkpoints/{checkpoint_id}_meta.json を作成

    Args:
        checkpoint_id: チェックポイントID
        project_id: プロジェクトID
        task_id: タスクID
        order_id: ORDER ID
        verbose: 詳細ログ出力

    Raises:
        CheckpointError: メタデータ保存失敗
    """
    checkpoint_dir = USER_DATA_PATH / "data" / "checkpoints"
    meta_file = checkpoint_dir / f"{checkpoint_id}_meta.json"

    # DBから現在のタスク状態を取得
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status, priority, assignee FROM tasks WHERE id = ? AND project_id = ?",
            (task_id, project_id)
        )
        task_row = cursor.fetchone()

        task_info = None
        if task_row:
            task_info = {
                "status": task_row[0],
                "priority": task_row[1],
                "assignee": task_row[2],
            }
    finally:
        conn.close()

    # メタデータ作成
    metadata = {
        "checkpoint_id": checkpoint_id,
        "created_at": datetime.now().isoformat(),
        "project_id": project_id,
        "task_id": task_id,
        "order_id": order_id,
        "task_info": task_info,
    }

    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    logger.debug(f"チェックポイントメタデータ保存完了: {meta_file}")


def list_checkpoints(
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    チェックポイント一覧を取得

    Args:
        project_id: プロジェクトID（フィルタ）
        task_id: タスクID（フィルタ）
        limit: 取得件数上限

    Returns:
        チェックポイント情報のリスト（新しい順）
    """
    checkpoint_dir = USER_DATA_PATH / "data" / "checkpoints"

    if not checkpoint_dir.exists():
        return []

    # メタデータファイルを収集
    meta_files = list(checkpoint_dir.glob("*_meta.json"))

    # 新しい順にソート
    meta_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    checkpoints: List[Dict[str, Any]] = []

    for meta_file in meta_files[:limit]:
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)

            # フィルタ適用
            if project_id and metadata.get("project_id") != project_id:
                continue
            if task_id and metadata.get("task_id") != task_id:
                continue

            # DBスナップショットファイル存在確認
            checkpoint_id = metadata["checkpoint_id"]
            db_snapshot = checkpoint_dir / f"{checkpoint_id}.db"
            metadata["db_snapshot_exists"] = db_snapshot.exists()
            metadata["db_snapshot_size"] = db_snapshot.stat().st_size if db_snapshot.exists() else 0

            checkpoints.append(metadata)

        except Exception as e:
            logger.warning(f"メタデータ読み込み失敗: {meta_file} - {e}")
            continue

    return checkpoints


def delete_old_checkpoints(keep_count: int = 10, dry_run: bool = False) -> int:
    """
    古いチェックポイントを削除

    Args:
        keep_count: 保持するチェックポイント数
        dry_run: 削除をシミュレート（実際には削除しない）

    Returns:
        削除したチェックポイント数
    """
    checkpoint_dir = USER_DATA_PATH / "data" / "checkpoints"

    if not checkpoint_dir.exists():
        return 0

    # メタデータファイルを取得（新しい順）
    meta_files = list(checkpoint_dir.glob("*_meta.json"))
    meta_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    # 保持する分を除外
    to_delete = meta_files[keep_count:]

    deleted_count = 0

    for meta_file in to_delete:
        try:
            # メタデータからcheckpoint_idを取得
            with open(meta_file, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            checkpoint_id = metadata["checkpoint_id"]

            # 削除対象ファイル
            files_to_delete = [
                checkpoint_dir / f"{checkpoint_id}.db",  # DBスナップショット
                meta_file,  # メタデータ
            ]

            # 削除実行
            for file_path in files_to_delete:
                if file_path.exists():
                    if not dry_run:
                        file_path.unlink()
                    logger.info(f"チェックポイント削除: {file_path}")
                    deleted_count += 1

        except Exception as e:
            logger.warning(f"チェックポイント削除失敗: {meta_file} - {e}")
            continue

    return deleted_count


def main():
    """CLI エントリーポイント"""
    import argparse

    parser = argparse.ArgumentParser(description="チェックポイント管理")
    subparsers = parser.add_subparsers(dest="command", help="コマンド")

    # create コマンド
    create_parser = subparsers.add_parser("create", help="チェックポイント作成")
    create_parser.add_argument("project_id", help="プロジェクトID")
    create_parser.add_argument("task_id", help="タスクID")
    create_parser.add_argument("--order-id", help="ORDER ID")
    create_parser.add_argument("--verbose", "-v", action="store_true", help="詳細ログ出力")

    # list コマンド
    list_parser = subparsers.add_parser("list", help="チェックポイント一覧")
    list_parser.add_argument("--project-id", help="プロジェクトID（フィルタ）")
    list_parser.add_argument("--task-id", help="タスクID（フィルタ）")
    list_parser.add_argument("--limit", type=int, default=10, help="取得件数上限")

    # cleanup コマンド
    cleanup_parser = subparsers.add_parser("cleanup", help="古いチェックポイント削除")
    cleanup_parser.add_argument("--keep", type=int, default=10, help="保持するチェックポイント数")
    cleanup_parser.add_argument("--dry-run", action="store_true", help="削除をシミュレート")

    args = parser.parse_args()

    # ロギング設定
    logging.basicConfig(
        level=logging.DEBUG if args.command == "create" and args.verbose else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    if args.command == "create":
        try:
            checkpoint_id = create_checkpoint(
                args.project_id,
                args.task_id,
                args.order_id,
                verbose=args.verbose
            )
            print(f"✓ チェックポイント作成完了: {checkpoint_id}")
            sys.exit(0)
        except CheckpointError as e:
            print(f"✗ エラー: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        checkpoints = list_checkpoints(
            args.project_id,
            args.task_id,
            args.limit
        )

        if not checkpoints:
            print("チェックポイントが見つかりません")
            sys.exit(0)

        print(f"チェックポイント一覧 ({len(checkpoints)}件)")
        for cp in checkpoints:
            print(f"  - {cp['checkpoint_id']}: {cp['project_id']}/{cp['task_id']} "
                  f"({cp.get('db_snapshot_size', 0):,} bytes, created={cp['created_at']})")
        sys.exit(0)

    elif args.command == "cleanup":
        deleted_count = delete_old_checkpoints(args.keep, args.dry_run)
        mode = "シミュレーション" if args.dry_run else "削除"
        print(f"✓ {mode}完了: {deleted_count}ファイル")
        sys.exit(0)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
