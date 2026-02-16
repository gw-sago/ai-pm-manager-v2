#!/usr/bin/env python3
"""
ファイルスナップショット管理モジュール

タスク実行前にファイル状態を保存し、失敗時にロールバック可能にする。
checkpoint/create.py（DB中心）とは独立した、ファイルレベルのスナップショット機構。

TASK_1093で統合される予定。

Usage:
    from worker.snapshot_manager import SnapshotManager

    sm = SnapshotManager("AI_PM_PJ")
    snapshot_id = sm.create_snapshot("TASK_1091", "ORDER_109")
    # ... タスク実行 ...
    # 失敗時:
    result = sm.restore_snapshot(snapshot_id)
"""

import hashlib
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# プロジェクトルートの解決
_current_dir = Path(__file__).resolve().parent
_package_root = _current_dir.parent
_project_root = _package_root.parent


class SnapshotError(Exception):
    """スナップショット操作エラー"""
    pass


class SnapshotManager:
    """ファイルスナップショットの作成・復元・管理"""

    def __init__(self, project_id: str, snapshot_dir: str = None):
        """
        Args:
            project_id: プロジェクトID
            snapshot_dir: スナップショット保存先（デフォルト: data/snapshots）
        """
        self.project_id = project_id
        # BUG_001対策: ミュータブルデフォルト引数を使わずNoneで受けてから設定
        if snapshot_dir is None:
            self.snapshot_dir = _project_root / "data" / "snapshots"
        else:
            self.snapshot_dir = Path(snapshot_dir)

    def create_snapshot(
        self,
        task_id: str,
        order_id: str,
        target_files: Optional[list] = None,
    ) -> str:
        """
        対象ファイルのスナップショットを作成

        Args:
            task_id: タスクID
            order_id: ORDER ID
            target_files: 対象ファイルパスのリスト（Noneの場合はORDER成果物ディレクトリ全体）

        Returns:
            snapshot_id: "{YYYYMMDD}_{HHMMSS}_{task_id}" 形式

        Raises:
            SnapshotError: スナップショット作成に失敗した場合
        """
        # BUG_001対策: target_filesがNoneの場合はここで初期化
        if target_files is None:
            target_files = self._collect_order_files(order_id)

        # 1. snapshot_id生成
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"{timestamp}_{task_id}"

        # 2. スナップショットディレクトリ作成
        snap_path = self.snapshot_dir / snapshot_id
        snap_path.mkdir(parents=True, exist_ok=True)

        logger.info(
            "スナップショット作成開始: %s (対象ファイル: %d件)",
            snapshot_id,
            len(target_files),
        )

        # 3. 各ファイルをコピーし、メタデータを収集
        files_metadata = []
        # 同名ファイル検出用
        seen_names: dict = {}

        for file_path_str in target_files:
            src = Path(file_path_str)
            if not src.exists():
                logger.warning("ファイルが存在しないためスキップ: %s", src)
                continue
            if not src.is_file():
                logger.warning("ディレクトリのためスキップ: %s", src)
                continue

            # スナップショット内の保存名を決定（フラット構造、同名はサブディレクトリ分離）
            base_name = src.name
            if base_name in seen_names:
                # 同名ファイルが既にある場合、連番サブディレクトリに格納
                seen_names[base_name] += 1
                sub_dir = snap_path / f"dup_{seen_names[base_name]}"
                sub_dir.mkdir(parents=True, exist_ok=True)
                dest = sub_dir / base_name
                snapshot_rel_path = f"dup_{seen_names[base_name]}/{base_name}"
            else:
                seen_names[base_name] = 0
                dest = snap_path / base_name
                snapshot_rel_path = base_name

            # shutil.copy2でメタデータ保持コピー
            try:
                shutil.copy2(str(src), str(dest))
            except OSError as e:
                logger.warning("ファイルコピー失敗: %s -> %s (%s)", src, dest, e)
                continue

            # メタデータ収集
            stat = src.stat()
            sha256 = self._compute_sha256(src)

            files_metadata.append({
                "original_path": str(src),
                "snapshot_path": snapshot_rel_path,
                "size": stat.st_size,
                "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "sha256": sha256,
            })

        # 4. metadata.json作成・保存
        total_size = sum(f["size"] for f in files_metadata)
        metadata = {
            "snapshot_id": snapshot_id,
            "task_id": task_id,
            "order_id": order_id,
            "project_id": self.project_id,
            "created_at": datetime.now().isoformat(),
            "files": files_metadata,
            "total_size": total_size,
            "file_count": len(files_metadata),
        }

        meta_path = snap_path / "metadata.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(
            "スナップショット作成完了: %s (%d files, %s bytes)",
            snapshot_id,
            len(files_metadata),
            f"{total_size:,}",
        )

        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> dict:
        """
        スナップショットからファイルを復元

        Args:
            snapshot_id: 復元するスナップショットのID

        Returns:
            {
                "success": bool,
                "restored_files": list,
                "errors": list,
                "backup_dir": str
            }

        Raises:
            SnapshotError: メタデータが見つからない場合
        """
        snap_path = self.snapshot_dir / snapshot_id
        meta_path = snap_path / "metadata.json"

        if not meta_path.exists():
            raise SnapshotError(f"メタデータが見つかりません: {meta_path}")

        # 1. metadata.json読み込み
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # 2. 現在のファイルをバックアップ
        backup_dir_name = f"{snapshot_id}_pre_restore"
        backup_dir = self.snapshot_dir / backup_dir_name
        backup_dir.mkdir(parents=True, exist_ok=True)

        restored_files = []
        errors = []

        for file_info in metadata.get("files", []):
            original_path = Path(file_info["original_path"])
            snapshot_rel = file_info["snapshot_path"]
            snapshot_file = snap_path / snapshot_rel
            expected_sha256 = file_info.get("sha256", "")

            # 現在のファイルをバックアップ（存在する場合のみ）
            if original_path.exists():
                backup_dest = backup_dir / snapshot_rel
                backup_dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(original_path), str(backup_dest))
                except OSError as e:
                    logger.warning(
                        "バックアップ失敗: %s (%s)", original_path, e
                    )

            # スナップショットからファイルを復元
            if not snapshot_file.exists():
                errors.append({
                    "file": str(original_path),
                    "error": f"スナップショットファイルが見つかりません: {snapshot_file}",
                })
                continue

            try:
                # 復元先ディレクトリを確保
                original_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(snapshot_file), str(original_path))

                # SHA256チェックサムで検証
                actual_sha256 = self._compute_sha256(original_path)
                if expected_sha256 and actual_sha256 != expected_sha256:
                    errors.append({
                        "file": str(original_path),
                        "error": (
                            f"チェックサム不一致: "
                            f"expected={expected_sha256[:16]}..., "
                            f"actual={actual_sha256[:16]}..."
                        ),
                    })
                else:
                    restored_files.append(str(original_path))

            except OSError as e:
                errors.append({
                    "file": str(original_path),
                    "error": str(e),
                })

        success = len(errors) == 0
        result = {
            "success": success,
            "restored_files": restored_files,
            "errors": errors,
            "backup_dir": str(backup_dir),
        }

        if success:
            logger.info(
                "スナップショット復元完了: %s (%d files)",
                snapshot_id,
                len(restored_files),
            )
        else:
            logger.warning(
                "スナップショット復元に一部エラー: %s (%d restored, %d errors)",
                snapshot_id,
                len(restored_files),
                len(errors),
            )

        return result

    def list_snapshots(self, task_id: str = None) -> list:
        """
        スナップショット一覧取得

        Args:
            task_id: 指定時はそのタスクのみフィルタ

        Returns:
            [{"snapshot_id": str, "task_id": str, "created_at": str,
              "file_count": int, "total_size": int}]
        """
        if not self.snapshot_dir.exists():
            return []

        snapshots = []

        for entry in self.snapshot_dir.iterdir():
            if not entry.is_dir():
                continue

            # _pre_restoreバックアップディレクトリは除外
            if entry.name.endswith("_pre_restore"):
                continue

            meta_path = entry / "metadata.json"
            if not meta_path.exists():
                continue

            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("メタデータ読み込み失敗: %s (%s)", meta_path, e)
                continue

            # task_idフィルタ
            if task_id and metadata.get("task_id") != task_id:
                continue

            snapshots.append({
                "snapshot_id": metadata.get("snapshot_id", entry.name),
                "task_id": metadata.get("task_id", ""),
                "created_at": metadata.get("created_at", ""),
                "file_count": metadata.get("file_count", 0),
                "total_size": metadata.get("total_size", 0),
            })

        # 新しい順にソート（created_at降順）
        snapshots.sort(key=lambda s: s["created_at"], reverse=True)

        return snapshots

    def cleanup_old_snapshots(self, keep_count: int = 10) -> int:
        """
        古いスナップショットを削除（新しい順にkeep_count件を残す）

        Args:
            keep_count: 保持するスナップショット数

        Returns:
            削除件数
        """
        snapshots = self.list_snapshots()

        if len(snapshots) <= keep_count:
            return 0

        # 古いスナップショット（keep_count件以降）を削除対象に
        to_delete = snapshots[keep_count:]
        deleted_count = 0

        for snap_info in to_delete:
            snap_id = snap_info["snapshot_id"]
            snap_path = self.snapshot_dir / snap_id

            if snap_path.exists():
                try:
                    shutil.rmtree(str(snap_path))
                    deleted_count += 1
                    logger.info("スナップショット削除: %s", snap_id)
                except OSError as e:
                    logger.warning(
                        "スナップショット削除失敗: %s (%s)", snap_id, e
                    )

            # 関連する_pre_restoreディレクトリも削除
            pre_restore_path = self.snapshot_dir / f"{snap_id}_pre_restore"
            if pre_restore_path.exists():
                try:
                    shutil.rmtree(str(pre_restore_path))
                except OSError as e:
                    logger.warning(
                        "バックアップディレクトリ削除失敗: %s (%s)",
                        pre_restore_path,
                        e,
                    )

        return deleted_count

    def get_snapshot_info(self, snapshot_id: str) -> Optional[dict]:
        """
        スナップショットのメタデータ取得

        Args:
            snapshot_id: スナップショットID

        Returns:
            メタデータのdict。存在しない場合はNone。
        """
        meta_path = self.snapshot_dir / snapshot_id / "metadata.json"

        if not meta_path.exists():
            return None

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("メタデータ読み込み失敗: %s (%s)", meta_path, e)
            return None

    def _compute_sha256(self, file_path: Path) -> str:
        """
        ファイルのSHA256チェックサムを計算

        Args:
            file_path: 対象ファイルのパス

        Returns:
            SHA256ハッシュ値（16進文字列）
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()

    def _collect_order_files(self, order_id: str) -> list:
        """
        ORDER成果物ディレクトリからファイルパスを収集

        Args:
            order_id: ORDER ID

        Returns:
            ファイルパスのリスト（文字列）
        """
        result_dir = (
            _project_root
            / "PROJECTS"
            / self.project_id
            / "RESULT"
            / order_id
        )

        if not result_dir.exists():
            logger.warning(
                "ORDER成果物ディレクトリが見つかりません: %s", result_dir
            )
            return []

        # 除外パターン
        exclude_patterns = [
            "__pycache__",
            ".pyc",
            ".git",
            ".DS_Store",
            "node_modules",
        ]

        files = []
        for file_path in result_dir.rglob("*"):
            if not file_path.is_file():
                continue
            # 除外パターンチェック
            path_str = str(file_path)
            if any(pat in path_str for pat in exclude_patterns):
                continue
            files.append(str(file_path))

        return files
