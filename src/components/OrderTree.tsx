import React, { useState, useEffect, useCallback } from 'react';
import type { Project, OrderInfo, ProjectStateChangedEvent } from '../preload';

interface OrderTreeProps {
  /** 選択中のプロジェクト */
  project: Project | null;
  /** 選択中のORDER ID */
  selectedOrderId?: string | null;
  /** ORDER選択時のコールバック */
  onOrderSelect?: (order: OrderInfo) => void;
  /** コンパクト表示モード（サイドバー展開時） */
  compact?: boolean;
  /** 折りたたみ状態 */
  collapsed?: boolean;
}

/**
 * ORDERステータスに応じたアイコンを表示
 */
const OrderStatusIcon: React.FC<{ status: string; compact?: boolean }> = ({ status, compact }) => {
  const iconSize = compact ? 'w-2 h-2' : 'w-3 h-3';

  switch (status.toUpperCase()) {
    case 'COMPLETED':
      // チェックマーク（緑）
      return (
        <span className={`${iconSize} text-green-500 flex-shrink-0`} title="COMPLETED">
          <svg fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
          </svg>
        </span>
      );
    case 'IN_PROGRESS':
      // 進行中（青い丸）
      return (
        <span className={`${iconSize} rounded-full bg-blue-500 flex-shrink-0`} title="IN_PROGRESS" />
      );
    case 'REVIEW':
      // レビュー中（黄色い丸）
      return (
        <span className={`${iconSize} rounded-full bg-yellow-500 flex-shrink-0`} title="REVIEW" />
      );
    case 'REWORK':
      // 差し戻し（赤い丸）
      return (
        <span className={`${iconSize} rounded-full bg-red-500 flex-shrink-0`} title="REWORK" />
      );
    default:
      // その他（グレーの丸）
      return (
        <span className={`${iconSize} rounded-full bg-gray-400 flex-shrink-0`} title={status} />
      );
  }
};

/**
 * ORDER一覧をツリー表示するコンポーネント
 *
 * プロジェクト選択時に、そのプロジェクトのORDER一覧を表示します。
 * タスク一覧はメインコンテンツエリアで確認するため、サイドバーでは非表示。
 */
export const OrderTree: React.FC<OrderTreeProps> = ({
  project,
  selectedOrderId,
  onOrderSelect,
  compact = false,
  collapsed = false,
}) => {
  // ORDERリスト（ステートで管理してリアルタイム更新対応）
  const [orders, setOrders] = useState<OrderInfo[]>([]);

  // プロジェクト変更時にORDERリストを更新
  useEffect(() => {
    if (project?.state?.orders) {
      // 新しい順（ORDER番号降順）でソート
      const sortedOrders = [...project.state.orders].sort((a, b) => {
        const aNum = parseInt(a.id.replace('ORDER_', ''), 10);
        const bNum = parseInt(b.id.replace('ORDER_', ''), 10);
        return bNum - aNum;
      });
      setOrders(sortedOrders);
    } else {
      setOrders([]);
    }
  }, [project]);

  // STATE変更イベントの購読
  useEffect(() => {
    if (!project) return;

    const handleStateChanged = (event: ProjectStateChangedEvent) => {
      if (event.projectName === project.name && event.state?.orders) {
        const sortedOrders = [...event.state.orders].sort((a, b) => {
          const aNum = parseInt(a.id.replace('ORDER_', ''), 10);
          const bNum = parseInt(b.id.replace('ORDER_', ''), 10);
          return bNum - aNum;
        });
        setOrders(sortedOrders);
      }
    };

    const unsubscribe = window.electronAPI.onProjectStateChanged(handleStateChanged);
    return () => {
      unsubscribe();
    };
  }, [project]);

  // メニュー更新イベントの購読（ORDER_063 / TASK_677）
  // ボタン操作・自動実行完了時にORDER一覧を自動更新
  useEffect(() => {
    if (!project) return;

    const refreshOrders = async () => {
      try {
        const freshState = await window.electronAPI.getProjectState(project.name);
        if (freshState?.orders) {
          const sortedOrders = [...freshState.orders].sort((a, b) => {
            const aNum = parseInt(a.id.replace('ORDER_', ''), 10);
            const bNum = parseInt(b.id.replace('ORDER_', ''), 10);
            return bNum - aNum;
          });
          setOrders(sortedOrders);
          console.log('[OrderTree] Orders refreshed for:', project.name, 'count:', sortedOrders.length);
        }
      } catch (error) {
        console.error('[OrderTree] Failed to refresh orders:', error);
      }
    };

    const unsubscribe = window.electronAPI.onMenuUpdate(() => {
      console.log('[OrderTree] menu:update event received, refreshing orders...');
      refreshOrders();
    });

    return () => {
      unsubscribe();
    };
  }, [project]);

  // DB変更イベントの購読（ORDER_004 / TASK_011）
  // スクリプト実行完了・タスクステータス変更時にORDER一覧を自動更新
  useEffect(() => {
    if (!project) return;

    const unsubscribe = window.electronAPI.onDbChanged((event) => {
      // 現在表示中のプロジェクトに関係するイベントのみ再フェッチ
      if (event.projectId === project.name) {
        console.log('[OrderTree] db:changed event received for project:', event.projectId, 'source:', event.source);
        // ORDER一覧を再取得
        window.electronAPI.getProjectState(project.name)
          .then((freshState) => {
            if (freshState?.orders) {
              const sortedOrders = [...freshState.orders].sort((a, b) => {
                const aNum = parseInt(a.id.replace('ORDER_', ''), 10);
                const bNum = parseInt(b.id.replace('ORDER_', ''), 10);
                return bNum - aNum;
              });
              setOrders(sortedOrders);
              console.log('[OrderTree] Orders refreshed via db:changed for:', project.name, 'count:', sortedOrders.length);
            }
          })
          .catch((error) => {
            console.error('[OrderTree] Failed to refresh orders via db:changed:', error);
          });
      }
    });

    return () => {
      unsubscribe();
    };
  }, [project]);

  /**
   * ORDER選択ハンドラ
   */
  const handleOrderClick = useCallback((order: OrderInfo) => {
    onOrderSelect?.(order);
  }, [onOrderSelect]);

  // プロジェクト未選択時
  if (!project) {
    if (collapsed) {
      return null;
    }
    return (
      <div className={`text-center py-2 ${compact ? 'px-1' : 'px-2'}`}>
        <p className="text-xs text-gray-400">
          {compact ? 'PJ選択' : 'プロジェクトを選択してください'}
        </p>
      </div>
    );
  }

  // ORDERがない場合
  if (orders.length === 0) {
    if (collapsed) {
      return null;
    }
    return (
      <div className={`text-center py-2 ${compact ? 'px-1' : 'px-2'}`}>
        <p className="text-xs text-gray-400">
          {compact ? 'なし' : 'ORDERがありません'}
        </p>
      </div>
    );
  }

  // 折りたたみ状態：アイコンのみ表示
  if (collapsed) {
    return (
      <div className="flex flex-col items-center space-y-1">
        {orders.slice(0, 5).map((order) => (
          <button
            key={order.id}
            onClick={() => handleOrderClick(order)}
            className={`w-8 h-8 flex items-center justify-center rounded-md transition-colors ${
              selectedOrderId === order.id
                ? 'bg-blue-100 ring-1 ring-blue-400'
                : 'hover:bg-gray-100'
            }`}
            title={`${order.id} (${order.status})`}
          >
            <OrderStatusIcon status={order.status} compact />
          </button>
        ))}
        {orders.length > 5 && (
          <span className="text-xs text-gray-400" title={`他 ${orders.length - 5} 件`}>
            +{orders.length - 5}
          </span>
        )}
      </div>
    );
  }

  // コンパクト表示（サイドバー展開時）
  return (
    <div className={compact ? '' : 'space-y-1'}>
      {/* ヘッダー */}
      <div className="flex items-center justify-between mb-1 px-1">
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
          ORDER
        </h4>
        <span className="text-xs text-gray-400">{orders.length}件</span>
      </div>

      {/* ORDER一覧 */}
      <div className={`space-y-0.5 ${compact ? 'max-h-60 overflow-y-auto' : ''}`}>
        {orders.map((order) => {
          const isSelected = selectedOrderId === order.id;
          const hasTasks = order.tasks && order.tasks.length > 0;

          return (
            <div key={order.id}>
              {/* ORDER行 */}
              <div
                className={`flex items-center py-1 px-2 rounded-md cursor-pointer transition-colors ${
                  isSelected
                    ? 'bg-blue-50 text-blue-700'
                    : 'hover:bg-gray-50 text-gray-700'
                }`}
                onClick={() => handleOrderClick(order)}
              >
                {/* ステータスアイコン */}
                <OrderStatusIcon status={order.status} compact={compact} />

                {/* ORDER ID + タイトル */}
                <span
                  className={`ml-2 ${compact ? 'text-xs' : 'text-sm'} font-medium truncate flex-1 min-w-0`}
                  title={order.title ? `${order.id.replace('ORDER_', '')}: ${order.title}` : order.id.replace('ORDER_', '')}
                >
                  {order.id.replace('ORDER_', '')}
                  {order.title && `: ${order.title}`}
                </span>

                {/* タスク数 */}
                {hasTasks && (
                  <span className="ml-2 text-xs text-gray-400 flex-shrink-0">
                    {order.tasks.filter(t => t.status === 'COMPLETED').length}/{order.tasks.length}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
