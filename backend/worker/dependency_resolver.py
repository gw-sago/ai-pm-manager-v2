"""
AI PM Framework - Dependency Resolver

タスク依存関係の動的解決エンジン。
DAG（有向非巡回グラフ）としての依存グラフ構築、トポロジカルソート、
クリティカルパス計算、および完了時の後続タスク自動QUEUED化を提供する。

主要コンポーネント:
- DependencyGraph: 依存グラフの構築・分析クラス
- resolve_on_completion(): タスク完了時の後続タスク自動解放
- unified_dependency_check(): parallel_detector / task_unblock 統一依存チェック
"""

import logging
from collections import deque
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from utils.db import (
    DatabaseError,
    execute_query,
    fetch_all,
    fetch_one,
    get_connection,
    close_connection,
    row_to_dict,
    rows_to_dicts,
    transaction,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DependencyGraph
# ---------------------------------------------------------------------------

class DependencyGraph:
    """
    タスク依存関係を DAG (Directed Acyclic Graph) として管理するクラス。

    ノード = タスクID、辺 = 依存関係（depends_on → task）。
    隣接リスト形式で保持し、トポロジカルソート・クリティカルパス計算・
    実行可能タスク検出をサポートする。
    """

    def __init__(self) -> None:
        # task_id -> そのタスクに依存している後続タスクID集合 (successors)
        self._successors: Dict[str, Set[str]] = {}
        # task_id -> そのタスクが依存している先行タスクID集合 (predecessors)
        self._predecessors: Dict[str, Set[str]] = {}
        # 全ノード集合
        self._nodes: Set[str] = set()
        # task_id -> status のマッピング (DB由来)
        self._statuses: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # グラフ構築
    # ------------------------------------------------------------------

    def build_graph(self, project_id: str, order_id: str) -> "DependencyGraph":
        """
        DBからタスク依存関係を読み込み、DAGを構築する。

        Args:
            project_id: プロジェクトID
            order_id: ORDER ID

        Returns:
            self (メソッドチェーン用)

        Raises:
            DatabaseError: DB読み込みエラー
        """
        conn = get_connection()
        try:
            # 1. ORDER内の全タスクを取得
            tasks = fetch_all(
                conn,
                """
                SELECT id, status
                FROM tasks
                WHERE project_id = ? AND order_id = ?
                """,
                (project_id, order_id),
            )

            for task in tasks:
                task_id: str = task["id"]
                self._nodes.add(task_id)
                self._statuses[task_id] = task["status"]
                # 空の隣接リストを初期化
                self._successors.setdefault(task_id, set())
                self._predecessors.setdefault(task_id, set())

            # 2. 依存関係を取得
            deps = fetch_all(
                conn,
                """
                SELECT td.task_id, td.depends_on_task_id
                FROM task_dependencies td
                JOIN tasks t ON td.task_id = t.id AND td.project_id = t.project_id
                WHERE td.project_id = ? AND t.order_id = ?
                """,
                (project_id, order_id),
            )

            for dep in deps:
                task_id = dep["task_id"]
                depends_on = dep["depends_on_task_id"]

                # ノードが未登録の場合も追加（ORDER跨ぎ依存の可能性）
                self._nodes.add(task_id)
                self._nodes.add(depends_on)
                self._successors.setdefault(depends_on, set()).add(task_id)
                self._predecessors.setdefault(task_id, set()).add(depends_on)
                self._successors.setdefault(task_id, set())
                self._predecessors.setdefault(depends_on, set())

            logger.info(
                f"DependencyGraph built: {len(self._nodes)} nodes, "
                f"{sum(len(s) for s in self._successors.values())} edges "
                f"(project={project_id}, order={order_id})"
            )
            return self

        finally:
            close_connection(conn)

    # ------------------------------------------------------------------
    # トポロジカルソート
    # ------------------------------------------------------------------

    def topological_sort(self) -> List[str]:
        """
        Kahnのアルゴリズムによるトポロジカルソートで実行順序を返す。

        Returns:
            タスクIDのリスト（依存関係を満たす実行順序）

        Raises:
            ValueError: グラフに循環がある場合
        """
        # 入次数を計算
        in_degree: Dict[str, int] = {
            node: len(self._predecessors.get(node, set()))
            for node in self._nodes
        }

        # 入次数0のノードをキューに追加
        queue: deque[str] = deque(
            node for node, degree in in_degree.items() if degree == 0
        )

        sorted_order: List[str] = []

        while queue:
            current = queue.popleft()
            sorted_order.append(current)

            for successor in self._successors.get(current, set()):
                in_degree[successor] -= 1
                if in_degree[successor] == 0:
                    queue.append(successor)

        if len(sorted_order) != len(self._nodes):
            visited = set(sorted_order)
            cycle_candidates = [n for n in self._nodes if n not in visited]
            raise ValueError(
                f"依存グラフに循環が検出されました。関連ノード: {cycle_candidates}"
            )

        return sorted_order

    # ------------------------------------------------------------------
    # クリティカルパス
    # ------------------------------------------------------------------

    def get_critical_path(self) -> List[str]:
        """
        最長依存チェーン（クリティカルパス）を計算する。

        各タスクの重みを1（均等）として、DAG上の最長パスを求める。
        トポロジカル順序でDPを行い、最長パスを逆追跡する。

        Returns:
            クリティカルパスを構成するタスクIDのリスト（開始 -> 終了の順）

        Raises:
            ValueError: グラフに循環がある場合（topological_sort経由）
        """
        topo_order = self.topological_sort()

        if not topo_order:
            return []

        # DP: 各ノードまでの最長距離と、その直前ノード
        dist: Dict[str, int] = {node: 0 for node in self._nodes}
        prev_node: Dict[str, Optional[str]] = {node: None for node in self._nodes}

        for node in topo_order:
            for successor in self._successors.get(node, set()):
                new_dist = dist[node] + 1
                if new_dist > dist[successor]:
                    dist[successor] = new_dist
                    prev_node[successor] = node

        # 最長距離のノードを特定
        end_node = max(dist, key=lambda n: dist[n])

        if dist[end_node] == 0:
            # 依存関係がない場合、任意の1ノードを返す
            return [end_node]

        # 逆追跡でパスを構築
        path: List[str] = []
        current: Optional[str] = end_node
        while current is not None:
            path.append(current)
            current = prev_node[current]

        path.reverse()
        return path

    # ------------------------------------------------------------------
    # 実行可能タスク検出
    # ------------------------------------------------------------------

    def get_ready_tasks(self, completed_task_ids: Set[str]) -> List[str]:
        """
        依存がすべてCOMPLETED済みのタスクリストを返す。

        Args:
            completed_task_ids: COMPLETED状態のタスクIDの集合

        Returns:
            実行可能なタスクIDのリスト
        """
        ready: List[str] = []

        for node in self._nodes:
            # 既に完了済みのタスクは除外
            if node in completed_task_ids:
                continue

            # ステータスが終了状態のものは除外
            status = self._statuses.get(node, "")
            if status in ("COMPLETED", "REJECTED", "CANCELLED", "SKIPPED"):
                continue

            # 全ての先行タスクがCOMPLETEDかチェック
            predecessors = self._predecessors.get(node, set())
            if predecessors and predecessors.issubset(completed_task_ids):
                ready.append(node)
            elif not predecessors:
                # 依存なし → 即実行可能（ただしステータスに応じて）
                if status in ("QUEUED", "BLOCKED"):
                    ready.append(node)

        return ready

    # ------------------------------------------------------------------
    # 後続タスク取得
    # ------------------------------------------------------------------

    def get_successors(self, task_id: str) -> List[str]:
        """
        直接後続タスクを返す。

        Args:
            task_id: タスクID

        Returns:
            直接後続タスクIDのリスト
        """
        return list(self._successors.get(task_id, set()))

    def get_all_descendants(self, task_id: str) -> List[str]:
        """
        推移的後続タスクを返す（再帰的にすべての子孫を探索）。

        BFS（幅優先探索）で推移閉包を計算する。

        Args:
            task_id: タスクID

        Returns:
            推移的後続タスクIDのリスト（task_id自身は含まない）
        """
        visited: Set[str] = set()
        queue: deque[str] = deque()

        # 直接後続タスクからBFS開始
        for successor in self._successors.get(task_id, set()):
            if successor not in visited:
                visited.add(successor)
                queue.append(successor)

        while queue:
            current = queue.popleft()
            for successor in self._successors.get(current, set()):
                if successor not in visited:
                    visited.add(successor)
                    queue.append(successor)

        return list(visited)

    # ------------------------------------------------------------------
    # ユーティリティ
    # ------------------------------------------------------------------

    @property
    def nodes(self) -> Set[str]:
        """グラフ内の全ノード（タスクID）"""
        return self._nodes.copy()

    @property
    def node_count(self) -> int:
        """ノード数"""
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """辺数"""
        return sum(len(s) for s in self._successors.values())

    def get_status(self, task_id: str) -> Optional[str]:
        """タスクのステータスを返す"""
        return self._statuses.get(task_id)

    def get_predecessors(self, task_id: str) -> List[str]:
        """直接先行タスクを返す"""
        return list(self._predecessors.get(task_id, set()))


# ---------------------------------------------------------------------------
# resolve_on_completion
# ---------------------------------------------------------------------------

def resolve_on_completion(
    project_id: str,
    order_id: str,
    completed_task_id: str,
) -> List[str]:
    """
    タスク完了時に後続タスクの依存を再評価し、BLOCKED -> QUEUED に遷移する。

    完了したタスクの直接後続タスクについて:
    - 全依存タスクがCOMPLETED であれば BLOCKED -> QUEUED に遷移
    - 遷移結果を change_history に記録

    Args:
        project_id: プロジェクトID
        order_id: ORDER ID
        completed_task_id: 完了したタスクID

    Returns:
        BLOCKED -> QUEUED に遷移したタスクIDのリスト

    Note:
        DONEではなくCOMPLETED（PM承認済み）が基準。
        これは task_unblock の _check_dependencies_completed と一貫した基準。
    """
    transitioned_task_ids: List[str] = []

    conn = get_connection()
    try:
        # 1. 完了タスクの後続タスクを取得
        successor_rows = fetch_all(
            conn,
            """
            SELECT DISTINCT td.task_id
            FROM task_dependencies td
            JOIN tasks t ON td.task_id = t.id AND td.project_id = t.project_id
            WHERE td.depends_on_task_id = ?
              AND td.project_id = ?
              AND t.order_id = ?
              AND t.status = 'BLOCKED'
            """,
            (completed_task_id, project_id, order_id),
        )

        if not successor_rows:
            logger.debug(
                f"resolve_on_completion: {completed_task_id} の "
                f"BLOCKED後続タスクなし"
            )
            return transitioned_task_ids

        logger.info(
            f"resolve_on_completion: {completed_task_id} の "
            f"BLOCKED後続タスク {len(successor_rows)} 件を評価"
        )

        # 2. 各後続タスクの依存をチェック
        now = datetime.now().isoformat()

        for row in successor_rows:
            successor_id: str = row["task_id"]

            # 全依存がCOMPLETEDかチェック
            pending = fetch_one(
                conn,
                """
                SELECT COUNT(*) as count
                FROM task_dependencies td
                JOIN tasks t ON td.depends_on_task_id = t.id
                                AND td.project_id = t.project_id
                WHERE td.task_id = ? AND td.project_id = ?
                  AND t.status != 'COMPLETED'
                """,
                (successor_id, project_id),
            )

            if pending and pending["count"] > 0:
                logger.debug(
                    f"resolve_on_completion: {successor_id} はまだ "
                    f"{pending['count']} 件の未完了依存あり"
                )
                continue

            # 3. BLOCKED -> QUEUED 遷移
            execute_query(
                conn,
                """
                UPDATE tasks
                SET status = 'QUEUED', updated_at = ?
                WHERE id = ? AND project_id = ? AND status = 'BLOCKED'
                """,
                (now, successor_id, project_id),
            )

            # 4. change_history に記録
            execute_query(
                conn,
                """
                INSERT INTO change_history
                    (entity_type, entity_id, field_name, old_value, new_value,
                     changed_by, change_reason, changed_at, project_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "task",
                    successor_id,
                    "status",
                    "BLOCKED",
                    "QUEUED",
                    "DependencyResolver",
                    f"依存タスク {completed_task_id} のCOMPLETEDにより自動解放",
                    now,
                    project_id,
                ),
            )

            transitioned_task_ids.append(successor_id)
            logger.info(
                f"resolve_on_completion: {successor_id} を "
                f"BLOCKED -> QUEUED に遷移 "
                f"(トリガー: {completed_task_id})"
            )

        conn.commit()

        if transitioned_task_ids:
            logger.info(
                f"resolve_on_completion: {len(transitioned_task_ids)} 件のタスクを "
                f"QUEUED化: {transitioned_task_ids}"
            )

    except Exception as e:
        logger.error(f"resolve_on_completion エラー: {e}", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        close_connection(conn)

    return transitioned_task_ids


# ---------------------------------------------------------------------------
# unified_dependency_check
# ---------------------------------------------------------------------------

def unified_dependency_check(
    project_id: str,
    task_id: str,
) -> Tuple[bool, List[str]]:
    """
    parallel_detector と task_unblock で使う統一された依存チェックロジック。

    基準: 依存タスクがすべて COMPLETED であること（DONEは不可）。
    これにより、PM承認を経ていないタスクの成果物に依存する後続タスクが
    誤って実行開始されることを防ぐ。

    Args:
        project_id: プロジェクトID
        task_id: チェック対象タスクID

    Returns:
        (is_ready, unmet_dependencies):
        - is_ready: 全依存がCOMPLETEDならTrue
        - unmet_dependencies: 未完了の依存タスクIDリスト
          （is_ready=True の場合は空リスト）

    Note:
        sqlite3.Row は .get() メソッドをサポートしない。
        直接インデックス row["key"] を使用すること。
    """
    conn = get_connection()
    try:
        # 未完了の依存タスクを取得
        unmet_rows = fetch_all(
            conn,
            """
            SELECT td.depends_on_task_id, t.status
            FROM task_dependencies td
            JOIN tasks t ON td.depends_on_task_id = t.id
                            AND td.project_id = t.project_id
            WHERE td.task_id = ? AND td.project_id = ?
              AND t.status != 'COMPLETED'
            """,
            (task_id, project_id),
        )

        if not unmet_rows:
            return (True, [])

        unmet_deps: List[str] = []
        for row in unmet_rows:
            dep_id: str = row["depends_on_task_id"]
            dep_status: str = row["status"]
            unmet_deps.append(dep_id)
            logger.debug(
                f"unified_dependency_check: {task_id} の依存 "
                f"{dep_id} は {dep_status} (COMPLETED以外)"
            )

        return (False, unmet_deps)

    finally:
        close_connection(conn)
