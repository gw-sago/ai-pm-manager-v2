/**
 * BacklogList - バックログ一覧コンポーネント
 *
 * バックログ項目の一覧表示とフィルタ・ソート機能を提供するコンポーネント。
 * BacklogFilterBarを統合し、以下の機能を実装:
 * - 優先度フィルタ（High/Medium/Low）
 * - ステータスフィルタ（TODO/IN_PROGRESS/DONE等）
 * - プロジェクト横断検索
 * - ソート機能（優先度順/作成日順/ステータス順）
 * - フィルタ状態の管理
 *
 * @module BacklogList
 * @created 2026-02-02
 * @order ORDER_021
 * @task TASK_328
 */

import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { BacklogFilterBar, type ProjectOption } from './BacklogFilterBar';
import type { BacklogFilters } from '../main/services/DashboardService';
import type { BacklogItem } from '../preload';
import { useBacklogActions } from '../hooks/useOrderActions';

// =============================================================================
// 型定義
// =============================================================================

/**
 * BacklogListのProps
 */
export interface BacklogListProps {
  /** プロジェクト名（単一プロジェクト表示用、オプション） */
  projectName?: string;
  /** 折りたたみ状態（後方互換性用） */
  collapsed?: boolean;
  /** 折りたたみ状態変更コールバック（後方互換性用） */
  onCollapsedChange?: (collapsed: boolean) => void;
  /** フィルタバーを表示するか（デフォルト: true） */
  showFilterBar?: boolean;
  /** コンパクトモードのフィルタバー（デフォルト: false） */
  compactFilterBar?: boolean;
  /** プロジェクト横断モード（全プロジェクトのバックログを表示） */
  crossProject?: boolean;
  /** 利用可能なプロジェクト一覧（プロジェクト横断モード用） */
  projects?: ProjectOption[];
  /** バックログ項目クリック時のコールバック */
  onItemClick?: (item: BacklogItem) => void;
  /** ORDER IDクリック時のコールバック（後方互換性用） */
  onOrderClick?: (orderId: string) => void;
  /** 初期フィルタ設定 */
  initialFilters?: BacklogFilters;
  /** 最大表示件数（デフォルト: 制限なし） */
  maxItems?: number;
  /** タイトル（オプション） */
  title?: string;
  /** 空の場合のメッセージ */
  emptyMessage?: string;
}

// =============================================================================
// 定数
// =============================================================================

/** 優先度の表示順序（ソート用） */
const PRIORITY_ORDER: Record<string, number> = {
  High: 0,
  Medium: 1,
  Low: 2,
};

/** ステータスの表示順序（ソート用） */
const STATUS_ORDER: Record<string, number> = {
  TODO: 0,
  IN_PROGRESS: 1,
  BLOCKED: 2,
  DONE: 3,
  CANCELLED: 4,
};

/** 優先度に対応する色クラス */
const PRIORITY_COLORS: Record<string, string> = {
  High: 'bg-red-100 text-red-700 border-red-200',
  Medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  Low: 'bg-green-100 text-green-700 border-green-200',
};

/** ステータスに対応する色クラス */
const STATUS_COLORS: Record<string, string> = {
  TODO: 'bg-gray-100 text-gray-600',
  IN_PROGRESS: 'bg-blue-100 text-blue-600',
  BLOCKED: 'bg-orange-100 text-orange-600',
  DONE: 'bg-green-100 text-green-600',
  CANCELLED: 'bg-gray-200 text-gray-500',
};

/** ORDERステータスに対応する色クラス（ORDER_032追加） */
const ORDER_STATUS_COLORS: Record<string, string> = {
  PLANNING: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  IN_PROGRESS: 'bg-blue-100 text-blue-700 border-blue-200',
  REVIEW: 'bg-purple-100 text-purple-700 border-purple-200',
  COMPLETED: 'bg-green-100 text-green-700 border-green-200',
  ON_HOLD: 'bg-orange-100 text-orange-700 border-orange-200',
  CANCELLED: 'bg-red-100 text-red-700 border-red-200',
};

/** ORDERステータスの日本語表示（ORDER_032追加） */
const ORDER_STATUS_LABELS: Record<string, string> = {
  PLANNING: '計画中',
  IN_PROGRESS: '実行中',
  REVIEW: 'レビュー',
  COMPLETED: '完了',
  ON_HOLD: '保留',
  CANCELLED: 'キャンセル',
};

// =============================================================================
// メインコンポーネント
// =============================================================================

/**
 * バックログ一覧コンポーネント
 *
 * バックログ項目の一覧を表示し、フィルタ・ソート機能を提供します。
 *
 * @example
 * ```tsx
 * // 単一プロジェクト表示（後方互換）
 * <BacklogList projectName="ai_pm_manager" />
 *
 * // プロジェクト横断表示（フィルタ付き）
 * <BacklogList
 *   crossProject
 *   projects={[
 *     { id: 'ai_pm_manager', name: 'AI PM Manager' },
 *     { id: 'other_project', name: 'Other Project' },
 *   ]}
 *   showFilterBar
 * />
 *
 * // カスタム初期フィルタ
 * <BacklogList
 *   initialFilters={{ priority: ['High'], sortBy: 'priority' }}
 *   onItemClick={(item) => console.log('Clicked:', item)}
 * />
 * ```
 */
export const BacklogList: React.FC<BacklogListProps> = ({
  projectName,
  collapsed = false,
  onCollapsedChange,
  showFilterBar = true,
  compactFilterBar = false,
  crossProject = false,
  projects = [],
  onItemClick,
  onOrderClick,
  initialFilters = {},
  maxItems,
  title = 'Backlog',
  emptyMessage = 'バックログ項目がありません',
}) => {
  // ==========================================================================
  // 状態管理
  // ==========================================================================

  /** フィルタ状態 */
  const [filters, setFilters] = useState<BacklogFilters>(initialFilters);
  /** バックログ項目リスト */
  const [items, setItems] = useState<BacklogItem[]>([]);
  /** ローディング状態 */
  const [isLoading, setIsLoading] = useState(true);
  /** エラー状態 */
  const [error, setError] = useState<string | null>(null);
  /** 折りたたみ状態（内部管理） */
  const [isCollapsed, setIsCollapsed] = useState(collapsed);
  /** トースト通知メッセージ（ORDER_051: 型追加） */
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  /** トースト種類（ORDER_051追加） */
  const [toastType, setToastType] = useState<'success' | 'error' | 'info'>('success');
  /** 実行中のジョブ（ORDER_039追加） */
  const [runningJobs, setRunningJobs] = useState<Set<string>>(new Set());
  // ORDER_053: 初回ロード完了フラグ（チラつき防止用）
  const [isInitialLoadDone, setIsInitialLoadDone] = useState(false);
  // ORDER_139: バックログ追加モーダル状態
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  // ORDER_139: 削除確認ダイアログ状態
  const [deleteConfirmItem, setDeleteConfirmItem] = useState<BacklogItem | null>(null);

  // ==========================================================================
  // 派生データ
  // ==========================================================================

  /**
   * フィルタ適用後のバックログ項目（クライアントサイドフィルタリング）
   */
  const filteredItems = useMemo(() => {
    let result = [...items];

    // 単一プロジェクトモードの場合、プロジェクトでフィルタ
    if (!crossProject && projectName) {
      result = result.filter((item) => item.projectId === projectName);
    }

    // クライアントサイドでの追加フィルタリング（API側で対応できない場合のフォールバック）
    if (filters.priority && filters.priority.length > 0) {
      result = result.filter((item) => (filters.priority as string[]).includes(item.priority));
    }

    if (filters.status && filters.status.length > 0) {
      result = result.filter((item) => filters.status!.includes(item.status));
    }

    if (filters.projectId) {
      result = result.filter((item) => item.projectId === filters.projectId);
    }

    return result;
  }, [items, filters, crossProject, projectName]);

  /**
   * ソート適用後のバックログ項目
   * ORDER_123: IN_PROGRESS最上部固定、優先度順ソート（High→Medium→Low）、同一優先度内はsort_order順
   */
  const sortedItems = useMemo(() => {
    const result = [...filteredItems];
    const { sortBy, sortOrder = 'desc' } = filters;

    // ORDER_123: デフォルトソートロジック（フィルタバーでソート指定がない場合）
    if (!sortBy) {
      // 1. IN_PROGRESSを最上部に固定
      // 2. 優先度順（High→Medium→Low）
      // 3. 同一優先度内はsort_order昇順（小さい番号が上）
      result.sort((a, b) => {
        // IN_PROGRESSを最優先
        const aInProgress = a.status === 'IN_PROGRESS' ? 0 : 1;
        const bInProgress = b.status === 'IN_PROGRESS' ? 0 : 1;
        if (aInProgress !== bInProgress) {
          return aInProgress - bInProgress;
        }

        // 優先度順
        const aPriority = PRIORITY_ORDER[a.priority] ?? 99;
        const bPriority = PRIORITY_ORDER[b.priority] ?? 99;
        if (aPriority !== bPriority) {
          return aPriority - bPriority;
        }

        // sort_order順（小さい番号が上）
        const aSortOrder = a.sortOrder ?? 999;
        const bSortOrder = b.sortOrder ?? 999;
        return aSortOrder - bSortOrder;
      });

      return result;
    }

    // フィルタバーでソートが指定されている場合
    result.sort((a, b) => {
      // IN_PROGRESSを常に最上部に固定
      const aInProgress = a.status === 'IN_PROGRESS' ? 0 : 1;
      const bInProgress = b.status === 'IN_PROGRESS' ? 0 : 1;
      if (aInProgress !== bInProgress) {
        return aInProgress - bInProgress;
      }

      let comparison = 0;

      switch (sortBy) {
        case 'priority':
          // High→Medium→Low の順（常に昇順）
          comparison = (PRIORITY_ORDER[a.priority] ?? 99) - (PRIORITY_ORDER[b.priority] ?? 99);
          if (comparison !== 0) return comparison;
          // 同一優先度内はsort_order昇順
          return (a.sortOrder ?? 999) - (b.sortOrder ?? 999);
        case 'status':
          comparison = (STATUS_ORDER[a.status] ?? 99) - (STATUS_ORDER[b.status] ?? 99);
          break;
        case 'createdAt':
          comparison = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
          break;
        case 'sortOrder':
          // sort_order昇順（常に小さい番号が上）
          return (a.sortOrder ?? 999) - (b.sortOrder ?? 999);
        default:
          return 0;
      }

      return sortOrder === 'asc' ? comparison : -comparison;
    });

    return result;
  }, [filteredItems, filters]);

  /**
   * 表示するバックログ項目
   * ORDER_123: ページネーション廃止、全件表示（スクロールリスト化）
   */
  const displayItems = useMemo(() => {
    // maxItemsが指定されている場合のみ制限を適用（後方互換性のため）
    if (maxItems && maxItems > 0) {
      return sortedItems.slice(0, maxItems);
    }
    return sortedItems;
  }, [sortedItems, maxItems]);

  // ==========================================================================
  // データ取得
  // ==========================================================================

  /**
   * バックログデータを取得
   *
   * ORDER_053: バックグラウンド更新対応
   * @param silent trueの場合、ローディング表示を抑制（定期リフレッシュ用）
   */
  const fetchBacklogs = useCallback(async (silent = false) => {
    // silentモード時、または初回ロード完了後はローディング表示をスキップ（チラつき防止）
    // ORDER_053: 初回ロード後はバックグラウンドで更新
    if (!silent && !isInitialLoadDone) {
      setIsLoading(true);
    }
    setError(null);

    try {
      // API呼び出し（フィルタ付き）
      const apiFilters: BacklogFilters = { ...filters };

      // 単一プロジェクトモードの場合、projectIdを設定
      if (!crossProject && projectName) {
        apiFilters.projectId = projectName;
      }

      const data = await window.electronAPI.getAllBacklogs(apiFilters);
      setItems(data);

      console.log('[BacklogList] Data loaded:', {
        count: data.length,
        filters: apiFilters,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'バックログの読み込みに失敗しました';
      setError(message);
      console.error('[BacklogList] Failed to load backlogs:', err);
    } finally {
      setIsLoading(false);
      // ORDER_053: 初回ロード完了をマーク
      if (!isInitialLoadDone) {
        setIsInitialLoadDone(true);
      }
    }
  }, [filters, crossProject, projectName, isInitialLoadDone]);

  // ORDER_144 / TASK_1185: 起動時のreorder呼び出しを削除
  // マウント時に自動でsort_orderが振り直されないようにする
  // （優先度自動整理は明示的なボタン操作でのみ実行する設計に変更）

  // バックエンドの実行中ジョブを同期（重複起動防止）- 初回 + 定期ポーリング
  useEffect(() => {
    const syncRunningJobs = () => {
      window.electronAPI.getRunningJobs()
        .then((jobs) => {
          const keys = new Set(jobs.map((j) => `${j.type}:${j.projectId}:${j.targetId}`));
          setRunningJobs(keys);
        })
        .catch((err) => {
          console.error('[BacklogList] Failed to sync running jobs:', err);
        });
    };

    syncRunningJobs();
    const interval = setInterval(syncRunningJobs, 5000);
    return () => clearInterval(interval);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // 初回読み込み＆フィルタ変更時の再取得
  useEffect(() => {
    fetchBacklogs();
  }, [fetchBacklogs]);

  // スクリプト実行完了イベントのリスナー（ORDER_039追加）
  useEffect(() => {
    // 完了イベントをリスニングして自動リフレッシュ
    // ORDER_053: silentモードでバックグラウンド更新（チラつき防止）
    const unsubscribe = window.electronAPI.onExecutionComplete((result) => {
      console.log('[BacklogList] Execution complete event received:', {
        type: result.type,
        success: result.success,
        targetId: result.targetId,
      });
      // 成功・失敗に関わらずリフレッシュ（状態が変わっている可能性があるため）
      fetchBacklogs(true);
    });

    return () => {
      unsubscribe();
    };
  }, [fetchBacklogs]);

  // プロジェクトリフレッシュイベントのリスナー（ORDER_051追加: リアルタイム性向上）
  useEffect(() => {
    // RefreshServiceからの更新通知をリスニング
    // ORDER_053: silentモードでバックグラウンド更新（チラつき防止）
    const unsubscribe = window.electronAPI.onRefreshed(() => {
      console.log('[BacklogList] Project refreshed event received, fetching backlogs (silent)...');
      fetchBacklogs(true);
    });

    return () => {
      unsubscribe();
    };
  }, [fetchBacklogs]);

  // ==========================================================================
  // イベントハンドラ
  // ==========================================================================

  /**
   * フィルタ変更ハンドラ
   */
  const handleFiltersChange = useCallback((newFilters: BacklogFilters) => {
    setFilters(newFilters);
  }, []);

  /**
   * 折りたたみトグルハンドラ
   */
  const handleToggleCollapsed = useCallback(() => {
    const newCollapsed = !isCollapsed;
    setIsCollapsed(newCollapsed);
    onCollapsedChange?.(newCollapsed);
  }, [isCollapsed, onCollapsedChange]);

  /**
   * バックログ項目クリックハンドラ
   */
  const handleItemClick = useCallback(
    (item: BacklogItem) => {
      onItemClick?.(item);
      // 後方互換性: relatedOrderIdがあればonOrderClickも呼び出す
      if (item.relatedOrderId && onOrderClick) {
        onOrderClick(item.relatedOrderId);
      }
    },
    [onItemClick, onOrderClick]
  );

  /**
   * トースト表示ハンドラ（ORDER_051: 型対応）
   */
  const handleShowToast = useCallback((message: string, type: 'success' | 'error' | 'info' = 'success') => {
    setToastMessage(message);
    setToastType(type);
    setTimeout(() => setToastMessage(null), 3000);
  }, []);

  /**
   * リフレッシュハンドラ（ORDER_144 / TASK_1188: 優先度自動整理＋再描画）
   * ORDER_053: 手動リフレッシュ時もsilentモードで実行（チラつき防止）
   * 初回ロード完了後は既存データを表示したまま更新
   */
  const handleRefresh = useCallback(async () => {
    // ローディング表示（既存データがある場合でもボタン押下時は表示）
    setIsLoading(true);

    try {
      // 優先度自動整理を実行（プロジェクトIDがある場合のみ）
      // crossProjectモードでない場合のみ実行
      if (!crossProject && projectName) {
        const result = await window.electronAPI.prioritizeBacklogs(projectName, {});

        if (result.success) {
          const updatedCount = result.updatedCount || 0;
          if (updatedCount > 0) {
            handleShowToast(`優先度を自動整理しました（${updatedCount}件更新）`, 'success');
          } else {
            handleShowToast('優先度は既に最適化されています', 'info');
          }
        } else {
          // エラーでも警告表示のみ（一覧取得は続行）
          console.warn('[BacklogList] 優先度整理失敗:', result.error);
          handleShowToast('優先度整理に失敗しました', 'error');
        }
      }
    } catch (err) {
      console.error('[BacklogList] 優先度整理エラー:', err);
      handleShowToast('優先度整理でエラーが発生しました', 'error');
    } finally {
      // 一覧を再取得
      await fetchBacklogs(isInitialLoadDone);
      setIsLoading(false);
    }
  }, [fetchBacklogs, isInitialLoadDone, crossProject, projectName, handleShowToast]);

  /**
   * PM実行ハンドラ（ORDER_039追加、ORDER_042でバックグラウンド実行化）
   * 実行を開始したら即座に返し、結果はFloatingProgressPanelで表示
   */
  const handleExecutePm = useCallback((projectId: string, backlogId: string) => {
    const jobKey = `pm:${projectId}:${backlogId}`;
    if (runningJobs.has(jobKey)) {
      return;
    }

    // ローカル状態で実行中フラグを立てる（UI即時反映用）
    setRunningJobs((prev) => new Set(prev).add(jobKey));
    handleShowToast(`PM処理を開始: ${backlogId}`, 'info');

    // バックグラウンドで実行（awaitしない）
    window.electronAPI.executePmProcess(projectId, backlogId)
      .then((result) => {
        if (result.success) {
          handleShowToast(`PM処理が完了しました: ${backlogId}`, 'success');
        } else {
          handleShowToast(`PM処理失敗: ${result.error || 'Unknown error'}`, 'error');
        }
        // 完了後にリフレッシュ（ORDER_053: silentモード）
        fetchBacklogs(true);
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : 'Unknown error';
        handleShowToast(`PM処理エラー: ${message}`, 'error');
        console.error('[BacklogList] PM execution error:', err);
      })
      .finally(() => {
        setRunningJobs((prev) => {
          const next = new Set(prev);
          next.delete(jobKey);
          return next;
        });
      });
  }, [runningJobs, handleShowToast, fetchBacklogs]);

  /**
   * Worker実行ハンドラ（ORDER_039追加、ORDER_042でバックグラウンド実行化）
   * 実行を開始したら即座に返し、結果はFloatingProgressPanelで表示
   */
  const handleExecuteWorker = useCallback((projectId: string, orderId: string) => {
    const jobKey = `worker:${projectId}:${orderId}`;
    if (runningJobs.has(jobKey)) {
      return;
    }

    // ローカル状態で実行中フラグを立てる（UI即時反映用）
    setRunningJobs((prev) => new Set(prev).add(jobKey));
    handleShowToast(`Worker処理を開始: ${orderId}`, 'info');

    // バックグラウンドで実行（awaitしない）
    window.electronAPI.executeWorkerProcess(projectId, orderId)
      .then((result) => {
        if (result.success) {
          handleShowToast(`Worker処理が完了しました: ${orderId}`, 'success');
        } else {
          handleShowToast(`Worker処理失敗: ${result.error || 'Unknown error'}`, 'error');
        }
        // 完了後にリフレッシュ（ORDER_053: silentモード）
        fetchBacklogs(true);
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : 'Unknown error';
        handleShowToast(`Worker処理エラー: ${message}`, 'error');
        console.error('[BacklogList] Worker execution error:', err);
      })
      .finally(() => {
        setRunningJobs((prev) => {
          const next = new Set(prev);
          next.delete(jobKey);
          return next;
        });
      });
  }, [runningJobs, handleShowToast, fetchBacklogs]);

  /**
   * 特定のジョブが実行中かどうかを確認（ORDER_039追加）
   */
  const isJobRunning = useCallback((type: 'pm' | 'worker', projectId: string, targetId: string): boolean => {
    return runningJobs.has(`${type}:${projectId}:${targetId}`);
  }, [runningJobs]);

  /**
   * バックログ追加モーダルを開く（ORDER_139追加）
   */
  const handleOpenAddModal = useCallback(() => {
    setIsAddModalOpen(true);
  }, []);

  /**
   * バックログ追加モーダルを閉じる（ORDER_139追加）
   */
  const handleCloseAddModal = useCallback(() => {
    setIsAddModalOpen(false);
  }, []);

  /**
   * バックログ追加完了ハンドラ（ORDER_139追加）
   */
  const handleAddComplete = useCallback(() => {
    setIsAddModalOpen(false);
    handleShowToast('バックログを追加しました', 'success');
    fetchBacklogs(true); // silentモードで再取得
  }, [handleShowToast, fetchBacklogs]);

  /**
   * バックログ削除確認ダイアログを開く（ORDER_139追加）
   */
  const handleOpenDeleteConfirm = useCallback((item: BacklogItem, e: React.MouseEvent) => {
    e.stopPropagation(); // 親のonClickを発火させない
    setDeleteConfirmItem(item);
  }, []);

  /**
   * バックログ削除確認ダイアログを閉じる（ORDER_139追加）
   */
  const handleCloseDeleteConfirm = useCallback(() => {
    setDeleteConfirmItem(null);
  }, []);

  /**
   * バックログ削除実行ハンドラ（ORDER_139追加）
   */
  const handleDeleteBacklog = useCallback(async () => {
    if (!deleteConfirmItem) return;

    try {
      // IPC呼び出し（TASK_1161で実装予定）
      await window.electronAPI.deleteBacklog(deleteConfirmItem.projectId, deleteConfirmItem.id);
      handleShowToast('バックログを削除しました', 'success');
      fetchBacklogs(true); // silentモードで再取得
    } catch (err) {
      const message = err instanceof Error ? err.message : 'バックログの削除に失敗しました';
      handleShowToast(message, 'error');
      console.error('[BacklogList] Failed to delete backlog:', err);
    } finally {
      setDeleteConfirmItem(null);
    }
  }, [deleteConfirmItem, handleShowToast, fetchBacklogs]);

  // ==========================================================================
  // レンダリング
  // ==========================================================================

  // 折りたたまれている場合
  if (isCollapsed) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
        <button
          onClick={handleToggleCollapsed}
          className="w-full flex items-center justify-between p-4 hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-2">
            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="font-medium text-gray-700">{title}</span>
            <span className="text-xs text-gray-400">({sortedItems.length} items)</span>
          </div>
        </button>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
      {/* ヘッダー */}
      <div className="flex items-center justify-between p-4 border-b border-gray-100">
        <div className="flex items-center gap-2">
          {onCollapsedChange && (
            <button
              onClick={handleToggleCollapsed}
              className="p-1 hover:bg-gray-100 rounded transition-colors"
            >
              <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          )}
          <h3 className="font-medium text-gray-800">{title}</h3>
          <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
            {displayItems.length}
            {maxItems && sortedItems.length > maxItems && ` / ${sortedItems.length}`}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* ORDER_139: 追加ボタン */}
          <button
            onClick={handleOpenAddModal}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-500 text-white text-sm rounded-lg hover:bg-blue-600 transition-colors"
            title="新規バックログを追加"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>追加</span>
          </button>
          {/* リフレッシュボタン */}
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className={`
              p-1.5 rounded-lg transition-colors
              ${isLoading ? 'text-gray-300' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'}
            `}
          >
            <svg
              className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* フィルタバー */}
      {showFilterBar && (
        <div className="p-4 border-b border-gray-100">
          <BacklogFilterBar
            filters={filters}
            onFiltersChange={handleFiltersChange}
            projects={crossProject ? projects : undefined}
            isLoading={isLoading}
            compact={compactFilterBar}
          />
        </div>
      )}

      {/* コンテンツ（ORDER_123: スクロールリスト化、max-h-[600px]でスクロール可能に） */}
      <div className="p-4 max-h-[600px] overflow-y-auto">
        {/* ローディング状態（初回ロードかつデータなしの場合のみスピナー表示） */}
        {/* ORDER_053: 既存データがある場合はチラつき防止のためスピナーを表示しない */}
        {isLoading && items.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <svg
              className="animate-spin h-6 w-6 text-blue-500"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
          </div>
        )}

        {/* エラー状態 */}
        {!isLoading && error && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center mb-3">
              <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>
            <p className="text-sm text-gray-500 mb-3">{error}</p>
            <button
              onClick={handleRefresh}
              className="px-3 py-1.5 bg-blue-500 text-white text-xs rounded-lg hover:bg-blue-600 transition-colors"
            >
              再試行
            </button>
          </div>
        )}

        {/* 空の状態 */}
        {!isLoading && !error && displayItems.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <div className="w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center mb-3">
              <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                />
              </svg>
            </div>
            <p className="text-sm text-gray-500">{emptyMessage}</p>
          </div>
        )}

        {/* バックログ項目リスト（ORDER_123: 全件表示、スクロール対応） */}
        {!isLoading && !error && displayItems.length > 0 && (
          <div className="space-y-2">
            {displayItems.map((item) => (
              <BacklogItemCard
                key={`${item.projectId}-${item.id}`}
                item={item}
                showProject={crossProject || !projectName}
                onClick={() => handleItemClick(item)}
                onCopyCommand={handleShowToast}
                onOrderIdClick={onOrderClick}
                isPmRunning={isJobRunning('pm', item.projectId, item.id)}
                isWorkerRunning={item.relatedOrderId ? isJobRunning('worker', item.projectId, item.relatedOrderId) : false}
                onExecutePm={handleExecutePm}
                onExecuteWorker={handleExecuteWorker}
                onDelete={handleOpenDeleteConfirm}
              />
            ))}
          </div>
        )}
      </div>

      {/* トースト通知（ORDER_051: 型対応） */}
      {toastMessage && (
        <Toast message={toastMessage} type={toastType} onClose={() => setToastMessage(null)} />
      )}

      {/* ORDER_139: バックログ追加モーダル */}
      {isAddModalOpen && (
        <BacklogAddModal
          onClose={handleCloseAddModal}
          onComplete={handleAddComplete}
          projectId={!crossProject && projectName ? projectName : undefined}
        />
      )}

      {/* ORDER_139: 削除確認ダイアログ */}
      {deleteConfirmItem && (
        <DeleteConfirmDialog
          item={deleteConfirmItem}
          onConfirm={handleDeleteBacklog}
          onCancel={handleCloseDeleteConfirm}
        />
      )}
    </div>
  );
};

// =============================================================================
// サブコンポーネント
// =============================================================================

/**
 * バックログ項目カード
 */
interface BacklogItemCardProps {
  item: BacklogItem;
  showProject?: boolean;
  onClick?: () => void;
  onCopyCommand?: (message: string) => void;
  /** ORDER IDクリック時のコールバック */
  onOrderIdClick?: (orderId: string) => void;
  /** PM実行中フラグ */
  isPmRunning?: boolean;
  /** Worker実行中フラグ */
  isWorkerRunning?: boolean;
  /** PM実行コールバック */
  onExecutePm?: (projectId: string, backlogId: string) => void;
  /** Worker実行コールバック */
  onExecuteWorker?: (projectId: string, orderId: string) => void;
  /** 削除ボタンクリックコールバック（ORDER_139追加） */
  onDelete?: (item: BacklogItem, e: React.MouseEvent) => void;
}

/**
 * ORDER_053: React.memoによる再レンダリング最適化
 *
 * itemのIDと主要プロパティ、実行状態フラグを比較し、
 * 変更がない場合は再レンダリングをスキップする
 */
const BacklogItemCard: React.FC<BacklogItemCardProps> = React.memo(({
  item,
  showProject = false,
  onClick,
  onCopyCommand,
  onOrderIdClick,
  isPmRunning = false,
  isWorkerRunning = false,
  onExecutePm,
  onExecuteWorker,
  onDelete,
}) => {
  const [isCopied, setIsCopied] = useState(false);
  const priorityColor = PRIORITY_COLORS[item.priority] || 'bg-gray-100 text-gray-600';
  const statusColor = STATUS_COLORS[item.status] || 'bg-gray-100 text-gray-600';

  // TASK_1137: useBacklogActionsを使用してボタン活性制御を精緻化
  const {
    canExecutePm,
    canExecuteWorker,
    pmDisabledReason,
    workerDisabledReason,
  } = useBacklogActions({
    backlogItem: item,
    isPmRunning,
    isWorkerRunning,
  });

  /**
   * コピーボタンクリックハンドラ
   */
  const handleCopyClick = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation(); // 親のonClickを発火させない
    const command = `/aipm-full-auto ${item.projectId} ${item.id}`;
    try {
      await navigator.clipboard.writeText(command);
      setIsCopied(true);
      onCopyCommand?.('コマンドをコピーしました');
      setTimeout(() => setIsCopied(false), 1500);
    } catch (err) {
      console.error('Failed to copy command:', err);
      onCopyCommand?.('コピーに失敗しました');
    }
  }, [item.projectId, item.id, onCopyCommand]);

  /**
   * ORDER IDクリックハンドラ
   */
  const handleOrderIdClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation(); // 親のonClickを発火させない
    if (item.relatedOrderId && onOrderIdClick) {
      onOrderIdClick(item.relatedOrderId);
    }
  }, [item.relatedOrderId, onOrderIdClick]);

  /**
   * PM実行ボタンクリックハンドラ（ORDER_039追加）
   */
  const handleExecutePm = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (canExecutePm && onExecutePm) {
      onExecutePm(item.projectId, item.id);
    }
  }, [canExecutePm, onExecutePm, item.projectId, item.id]);

  /**
   * Worker実行ボタンクリックハンドラ（ORDER_039追加）
   */
  const handleExecuteWorker = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (canExecuteWorker && onExecuteWorker && item.relatedOrderId) {
      onExecuteWorker(item.projectId, item.relatedOrderId);
    }
  }, [canExecuteWorker, onExecuteWorker, item.projectId, item.relatedOrderId]);

  /**
   * 削除ボタンクリックハンドラ（ORDER_139追加）
   */
  const handleDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete) {
      onDelete(item, e);
    }
  }, [onDelete, item]);

  /**
   * 優先度バッジクリックハンドラ（ORDER_139 / TASK_1164追加）
   * High→Medium→Low→Highの順で優先度を切り替える
   */
  const handlePriorityClick = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();

    // 優先度の循環ロジック: High→Medium→Low→High
    const priorityOrder: Array<'High' | 'Medium' | 'Low'> = ['High', 'Medium', 'Low'];
    const currentIndex = priorityOrder.indexOf(item.priority as 'High' | 'Medium' | 'Low');
    const nextIndex = (currentIndex + 1) % priorityOrder.length;
    const nextPriority = priorityOrder[nextIndex];

    try {
      // updateBacklog IPCを呼び出して優先度を更新
      await window.electronAPI.updateBacklog(item.projectId, item.id, {
        priority: nextPriority,
      });

      // 成功時にトースト通知（親コンポーネントから渡される場合）
      onCopyCommand?.(`優先度を${nextPriority}に変更しました`);
    } catch (err) {
      console.error('[BacklogItemCard] Failed to update priority:', err);
      onCopyCommand?.('優先度の変更に失敗しました');
    }
  }, [item.priority, item.projectId, item.id, onCopyCommand]);

  // ORDER情報の取得
  const orderStatusColor = item.orderStatus
    ? ORDER_STATUS_COLORS[item.orderStatus] || 'bg-gray-100 text-gray-600 border-gray-200'
    : '';
  const orderStatusLabel = item.orderStatus
    ? ORDER_STATUS_LABELS[item.orderStatus] || item.orderStatus
    : '';
  const hasOrder = !!item.relatedOrderId;
  const progressPercent = item.progressPercent ?? 0;

  // 実行中かどうか（ORDER_051: パルスアニメーション用）
  const isRunning = isPmRunning || isWorkerRunning;

  return (
    <div
      onClick={onClick}
      className={`
        p-3 rounded-lg border bg-gray-50
        hover:bg-white hover:border-gray-200 hover:shadow-sm
        transition-all cursor-pointer
        ${isRunning
          ? 'border-blue-300 bg-blue-50 animate-pulse'
          : item.status === 'IN_PROGRESS'
            ? 'border-blue-400 bg-blue-50 shadow-sm'
            : 'border-gray-100'
        }
      `}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          {/* プロジェクト名（横断モード時）& BACKLOG ID */}
          <div className="flex items-center gap-2 mb-1">
            {showProject && (
              <span className="text-[10px] text-gray-400">{item.projectId}</span>
            )}
            {/* BACKLOG ID（ORDER_034追加） */}
            <span className="text-[10px] text-purple-600 font-medium bg-purple-50 px-1.5 py-0.5 rounded">
              {item.id}
            </span>
            {/* sort_order表示（ORDER_106: TASK_990追加） */}
            <span className="text-[10px] text-gray-400 font-mono">
              {item.sortOrder != null && item.sortOrder !== 999 ? `#${item.sortOrder}` : '-'}
            </span>
          </div>
          {/* タイトル */}
          <div className="text-sm text-gray-800 font-medium truncate">{item.title}</div>
          {/* 説明（あれば） */}
          {item.description && (
            <div className="text-xs text-gray-500 mt-1 line-clamp-2">{item.description}</div>
          )}
          {/* ORDER紐付け情報（ORDER_032追加） */}
          {hasOrder ? (
            <div className="flex items-center gap-2 mt-2">
              {/* ORDER ID（クリック可能） */}
              <button
                onClick={handleOrderIdClick}
                className="text-[10px] text-blue-600 font-medium bg-blue-50 px-1.5 py-0.5 rounded hover:bg-blue-100 hover:text-blue-700 transition-colors cursor-pointer"
                title="ORDERを選択"
              >
                {item.relatedOrderId}
              </button>
              {/* ORDERステータスバッジ */}
              {item.orderStatus && (
                <span className={`inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded border ${orderStatusColor}`}>
                  {orderStatusLabel}
                </span>
              )}
              {/* 進捗率（タスクがある場合のみ） */}
              {(item.totalTasks ?? 0) > 0 && (
                <span className="text-[10px] text-gray-500">
                  {item.completedTasks}/{item.totalTasks} ({progressPercent}%)
                </span>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                未着手
              </span>
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-1.5">
          {/* PM実行ボタン（ORDER_039追加、ORDER_123でツールチップ拡張） */}
          {!item.relatedOrderId && (
            <button
              onClick={handleExecutePm}
              disabled={!canExecutePm}
              title={
                canExecutePm
                  ? "PM処理を実行（ORDER化→PM）"
                  : pmDisabledReason
              }
              aria-label="PM処理を実行"
              className={`
                flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors
                ${isPmRunning
                  ? 'bg-blue-100 text-blue-600 cursor-wait'
                  : canExecutePm
                    ? 'bg-green-100 text-green-700 hover:bg-green-200'
                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                }
              `}
            >
              {isPmRunning ? (
                <>
                  <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>PM...</span>
                </>
              ) : (
                <>
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>PM</span>
                </>
              )}
            </button>
          )}
          {/* Worker実行ボタン（ORDER_039追加、TASK_1137でツールチップ拡張） */}
          {item.relatedOrderId && item.orderStatus === 'IN_PROGRESS' && (
            <button
              onClick={handleExecuteWorker}
              disabled={!canExecuteWorker}
              title={canExecuteWorker ? "Worker処理を並列実行" : workerDisabledReason}
              aria-label="Worker処理を実行"
              className={`
                flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition-colors
                ${isWorkerRunning
                  ? 'bg-blue-100 text-blue-600 cursor-wait'
                  : canExecuteWorker
                    ? 'bg-indigo-100 text-indigo-700 hover:bg-indigo-200'
                    : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                }
              `}
            >
              {isWorkerRunning ? (
                <>
                  <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Worker...</span>
                </>
              ) : (
                <>
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <span>Worker</span>
                </>
              )}
            </button>
          )}
          {/* コピーボタン */}
          <button
            onClick={handleCopyClick}
            title="フルオート実行コマンドをコピー"
            aria-label="フルオート実行コマンドをコピー"
            className={`
              p-1 rounded transition-colors
              ${isCopied
                ? 'bg-green-100 text-green-600'
                : 'bg-gray-100 text-gray-500 hover:bg-blue-100 hover:text-blue-600'
              }
            `}
          >
            {isCopied ? (
              // チェックマークアイコン
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              // クリップボードアイコン
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
              </svg>
            )}
          </button>
          {/* ORDER_139: 削除ボタン */}
          <button
            onClick={handleDelete}
            title="バックログを削除"
            aria-label="バックログを削除"
            className="p-1 rounded transition-colors bg-gray-100 text-gray-500 hover:bg-red-100 hover:text-red-600"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
          </button>
          {/* 優先度バッジ（ORDER_139 / TASK_1164: クリック可能に変更） */}
          <button
            onClick={handlePriorityClick}
            title="クリックで優先度を切り替え（High→Medium→Low→High）"
            className={`inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded border ${priorityColor} cursor-pointer hover:opacity-80 transition-opacity`}
          >
            {item.priority}
          </button>
          {/* ステータスバッジ */}
          <span className={`inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded ${statusColor}`}>
            {item.status}
          </span>
        </div>
      </div>
      {/* 進捗バー（ORDER紐付けがあり、タスクがある場合のみ）ORDER_032追加 */}
      {hasOrder && (item.totalTasks ?? 0) > 0 && (
        <div className="mt-2">
          <div className="w-full h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-300 ${
                progressPercent === 100 ? 'bg-green-500' : 'bg-blue-500'
              }`}
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}
      {/* 作成日 */}
      <div className="flex items-center justify-between mt-2 text-[10px] text-gray-400">
        <span>Created: {formatDate(item.createdAt)}</span>
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  // ORDER_053: カスタム比較関数でメモ化を最適化
  // 変更がない場合はtrueを返して再レンダリングをスキップ
  // ORDER_139 / TASK_1164: 優先度変更検知のためpriority比較を維持
  return (
    prevProps.item.id === nextProps.item.id &&
    prevProps.item.status === nextProps.item.status &&
    prevProps.item.priority === nextProps.item.priority &&
    prevProps.item.relatedOrderId === nextProps.item.relatedOrderId &&
    prevProps.item.orderStatus === nextProps.item.orderStatus &&
    prevProps.item.progressPercent === nextProps.item.progressPercent &&
    prevProps.item.completedTasks === nextProps.item.completedTasks &&
    prevProps.item.totalTasks === nextProps.item.totalTasks &&
    prevProps.showProject === nextProps.showProject &&
    prevProps.isPmRunning === nextProps.isPmRunning &&
    prevProps.isWorkerRunning === nextProps.isWorkerRunning &&
    prevProps.onDelete === nextProps.onDelete
  );
});

// コンポーネント名を明示（デバッグ用）
BacklogItemCard.displayName = 'BacklogItemCard';

/**
 * トースト通知コンポーネント（ORDER_051: 成功/エラー色分け対応）
 *
 * - 成功: 緑アイコン + グレー背景
 * - エラー: 赤アイコン + 赤背景
 * - 情報: 青アイコン + グレー背景
 */
interface ToastProps {
  message: string;
  onClose: () => void;
  /** トーストの種類（デフォルト: success） */
  type?: 'success' | 'error' | 'info';
}

const Toast: React.FC<ToastProps> = ({ message, onClose, type = 'success' }) => {
  // タイプ別のスタイル設定
  const styles = {
    success: {
      bg: 'bg-gray-800',
      icon: 'text-green-400',
      iconPath: 'M5 13l4 4L19 7',
    },
    error: {
      bg: 'bg-red-600',
      icon: 'text-white',
      iconPath: 'M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    },
    info: {
      bg: 'bg-blue-600',
      icon: 'text-white',
      iconPath: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
    },
  };

  const style = styles[type];

  return (
    <div className="fixed bottom-4 right-4 z-50 animate-fade-in">
      <div className={`flex items-center gap-2 px-4 py-3 ${style.bg} text-white text-sm rounded-lg shadow-lg`}>
        <svg className={`w-4 h-4 ${style.icon}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={style.iconPath} />
        </svg>
        <span>{message}</span>
        <button
          onClick={onClose}
          className="ml-2 p-0.5 hover:bg-white/20 rounded transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
};

/**
 * バックログ追加モーダル（ORDER_139追加）
 * TASK_1160で実装されるBacklogAddFormをラップするモーダルダイアログ
 */
interface BacklogAddModalProps {
  onClose: () => void;
  onComplete: () => void;
  projectId?: string;
}

const BacklogAddModal: React.FC<BacklogAddModalProps> = ({ onClose, onComplete, projectId }) => {
  // BacklogAddFormコンポーネントが存在するかチェック
  const BacklogAddFormModule = React.useMemo(() => {
    try {
      // 動的インポートは非同期なので、ここでは存在チェックのみ
      // 実際のコンポーネントはTASK_1160で実装される想定
      return null;
    } catch {
      return null;
    }
  }, []);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto m-4">
        {/* ヘッダー */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-800">新規バックログ追加</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 rounded transition-colors"
          >
            <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        {/* コンテンツ */}
        <div className="p-4">
          {BacklogAddFormModule ? (
            // TASK_1160で実装されるBacklogAddFormを表示
            <div>BacklogAddForm placeholder</div>
          ) : (
            // BacklogAddFormが未実装の場合のプレースホルダー
            <div className="text-center py-8">
              <div className="w-16 h-16 bg-yellow-100 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg className="w-8 h-8 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <p className="text-sm text-gray-600 mb-2">BacklogAddFormコンポーネントは準備中です</p>
              <p className="text-xs text-gray-500">TASK_1160で実装予定</p>
              <div className="mt-4">
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
                >
                  閉じる
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/**
 * 削除確認ダイアログ（ORDER_139追加）
 */
interface DeleteConfirmDialogProps {
  item: BacklogItem;
  onConfirm: () => void;
  onCancel: () => void;
}

const DeleteConfirmDialog: React.FC<DeleteConfirmDialogProps> = ({ item, onConfirm, onCancel }) => {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
      <div className="bg-white rounded-lg shadow-xl max-w-md w-full m-4">
        {/* ヘッダー */}
        <div className="flex items-center gap-3 p-4 border-b border-gray-200">
          <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
            <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="text-lg font-semibold text-gray-800">バックログを削除</h2>
        </div>
        {/* コンテンツ */}
        <div className="p-4">
          <p className="text-sm text-gray-700 mb-4">
            以下のバックログを削除してもよろしいですか？
          </p>
          <div className="bg-gray-50 rounded-lg p-3 mb-4">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs text-purple-600 font-medium bg-purple-50 px-2 py-0.5 rounded">
                {item.id}
              </span>
              {item.relatedOrderId && (
                <span className="text-xs text-blue-600 font-medium bg-blue-50 px-2 py-0.5 rounded">
                  {item.relatedOrderId}
                </span>
              )}
            </div>
            <p className="text-sm font-medium text-gray-800 mb-1">{item.title}</p>
            {item.description && (
              <p className="text-xs text-gray-600 line-clamp-2">{item.description}</p>
            )}
          </div>
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 mb-4">
            <p className="text-xs text-yellow-800">
              <strong>注意:</strong> この操作は取り消せません。バックログのステータスがCANCELLEDに変更されます。
            </p>
          </div>
        </div>
        {/* フッター */}
        <div className="flex items-center justify-end gap-2 p-4 border-t border-gray-200">
          <button
            onClick={onCancel}
            className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
          >
            キャンセル
          </button>
          <button
            onClick={onConfirm}
            className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
          >
            削除
          </button>
        </div>
      </div>
    </div>
  );
};

// =============================================================================
// ユーティリティ関数
// =============================================================================

/**
 * 日付フォーマット
 */
function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

// =============================================================================
// デフォルトエクスポート
// =============================================================================

export default BacklogList;
