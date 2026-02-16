/**
 * OrderReleaseSection - ORDER詳細画面のリリース情報セクション
 *
 * ORDER_071: リリース状態表示の実データ連携
 * TASK_709: ReleaseInfoCard連携実装
 * ORDER_108 / TASK_995: リリース実行ボタン・確認ダイアログ・トースト通知
 *
 * ReleaseInfoCardコンポーネントを使用して、ORDER単位のリリース情報を
 * ReleaseService経由で取得・表示するセクションコンポーネント。
 * リリース実行ボタン、dry-run確認ダイアログ、トースト通知機能を含む。
 */

import React, { useEffect, useState, useCallback } from 'react';
import type { OrderReleaseInfo, ReleaseDryRunResult, ReleaseResult, TaskInfo } from '../preload';
import { ReleaseInfoCard } from './ReleaseInfoCard';

interface OrderReleaseSectionProps {
  /** プロジェクトID */
  projectId: string;
  /** ORDER ID */
  orderId: string;
  /** 関連バックログID一覧（オプション） */
  relatedBacklogIds?: string[];
  /** ORDER内タスク一覧（canRelease判定用） */
  tasks?: TaskInfo[];
}

/** トースト通知の型 */
interface Toast {
  type: 'success' | 'error';
  message: string;
}

/**
 * ORDER詳細画面のリリース情報セクション
 */
export const OrderReleaseSection: React.FC<OrderReleaseSectionProps> = ({
  projectId,
  orderId,
  relatedBacklogIds = [],
  tasks = [],
}) => {
  // リリース情報
  const [releaseInfo, setReleaseInfo] = useState<OrderReleaseInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 確認ダイアログ
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [dryRunResult, setDryRunResult] = useState<ReleaseDryRunResult | null>(null);
  const [dryRunLoading, setDryRunLoading] = useState(false);

  // リリース実行
  const [executing, setExecuting] = useState(false);

  // トースト通知
  const [toast, setToast] = useState<Toast | null>(null);

  // canRelease判定: 全タスクがCOMPLETED or DONE
  const canRelease = tasks.length > 0 && tasks.every(
    (t) => t.status === 'COMPLETED' || t.status === 'DONE'
  );

  // リリース済み判定
  const isReleased = releaseInfo?.hasRelease ?? false;

  // リリース不可理由
  const getDisabledReason = (): string | null => {
    if (tasks.length === 0) return 'タスクがありません';
    const incomplete = tasks.filter(
      (t) => t.status !== 'COMPLETED' && t.status !== 'DONE'
    );
    if (incomplete.length > 0) {
      return `未完了タスクがあります: ${incomplete.map((t) => t.id).join(', ')}`;
    }
    return null;
  };

  // リリース情報を取得
  const fetchReleaseInfo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const info = await window.electronAPI.getOrderReleaseInfo(projectId, orderId);
      setReleaseInfo(info);
    } catch (err) {
      console.error('[OrderReleaseSection] Failed to fetch release info:', err);
      setError('リリース情報の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  }, [projectId, orderId]);

  useEffect(() => {
    fetchReleaseInfo();
  }, [fetchReleaseInfo]);

  // トースト自動消去
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [toast]);

  // dry-run実行→確認ダイアログ表示
  const handleReleaseClick = async () => {
    setDryRunLoading(true);
    setDryRunResult(null);
    try {
      const result = await window.electronAPI.executeReleaseDryRun(projectId, orderId);
      setDryRunResult(result);
      if (result.success) {
        setShowConfirmDialog(true);
      } else {
        setToast({ type: 'error', message: `dry-runに失敗しました: ${result.error || '不明なエラー'}` });
      }
    } catch (err) {
      console.error('[OrderReleaseSection] Dry-run failed:', err);
      setToast({ type: 'error', message: 'dry-runの実行中にエラーが発生しました' });
    } finally {
      setDryRunLoading(false);
    }
  };

  // リリース実行
  const handleConfirmRelease = async () => {
    setExecuting(true);
    try {
      const result: ReleaseResult = await window.electronAPI.executeRelease(projectId, orderId);
      setShowConfirmDialog(false);
      if (result.success) {
        setToast({ type: 'success', message: 'リリースが完了しました' });
        // リリース情報をリロード
        await fetchReleaseInfo();
      } else {
        setToast({ type: 'error', message: `リリースに失敗しました: ${result.error || '不明なエラー'}` });
      }
    } catch (err) {
      console.error('[OrderReleaseSection] Release execution failed:', err);
      setShowConfirmDialog(false);
      setToast({ type: 'error', message: 'リリースの実行中にエラーが発生しました' });
    } finally {
      setExecuting(false);
    }
  };

  // ダイアログキャンセル
  const handleCancelDialog = () => {
    setShowConfirmDialog(false);
    setDryRunResult(null);
  };

  // ローディング表示
  if (loading) {
    return (
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">リリース情報</h3>
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 flex items-center justify-center">
          <svg
            className="animate-spin h-5 w-5 text-gray-400 mr-2"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span className="text-sm text-gray-500">読み込み中...</span>
        </div>
      </div>
    );
  }

  // エラー表示
  if (error) {
    return (
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-gray-700 mb-2">リリース情報</h3>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-sm text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  const disabledReason = getDisabledReason();

  return (
    <div className="mb-4">
      <h3 className="text-sm font-semibold text-gray-700 mb-2">リリース情報</h3>

      {/* リリース情報カード */}
      {releaseInfo && (
        <ReleaseInfoCard
          releaseInfo={releaseInfo}
          relatedBacklogIds={relatedBacklogIds}
        />
      )}

      {/* リリース実行ボタン（未リリース時のみ表示） */}
      {!isReleased && (
        <div className="mt-2">
          <button
            onClick={handleReleaseClick}
            disabled={!canRelease || dryRunLoading || executing}
            className={`inline-flex items-center px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              canRelease && !dryRunLoading && !executing
                ? 'bg-blue-600 text-white hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }`}
            title={disabledReason || 'リリースを実行します'}
          >
            {dryRunLoading ? (
              <>
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                確認中...
              </>
            ) : (
              <>
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
                リリース実行
              </>
            )}
          </button>
          {/* 無効理由のツールチップ */}
          {disabledReason && (
            <p className="mt-1 text-xs text-gray-500">{disabledReason}</p>
          )}
        </div>
      )}

      {/* リリース済みバッジ */}
      {isReleased && (
        <div className="mt-2">
          <span className="inline-flex items-center px-3 py-1 text-sm font-medium bg-green-100 text-green-800 rounded-full">
            <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            リリース済み
          </span>
        </div>
      )}

      {/* 確認ダイアログ（モーダル） */}
      {showConfirmDialog && dryRunResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50">
          <div className="bg-white rounded-lg shadow-xl max-w-md w-full mx-4 overflow-hidden">
            {/* ヘッダー */}
            <div className="px-6 py-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">リリース確認</h3>
            </div>

            {/* コンテンツ */}
            <div className="px-6 py-4 space-y-3">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">ORDER</span>
                <span className="font-medium text-gray-900">{dryRunResult.orderId}</span>
              </div>
              {dryRunResult.orderTitle && (
                <div className="flex justify-between text-sm">
                  <span className="text-gray-500">タイトル</span>
                  <span className="font-medium text-gray-900 text-right max-w-[60%]">{dryRunResult.orderTitle}</span>
                </div>
              )}
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">対象ファイル数</span>
                <span className="font-medium text-gray-900">{dryRunResult.fileCount ?? 0} ファイル</span>
              </div>

              {/* ファイル一覧 */}
              {dryRunResult.files && dryRunResult.files.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-gray-500 mb-1">対象ファイル:</p>
                  <div className="max-h-32 overflow-y-auto bg-gray-50 rounded p-2">
                    {dryRunResult.files.map((f, i) => (
                      <div key={i} className="text-xs text-gray-600 flex items-center py-0.5">
                        <span className={`inline-block w-12 text-center text-xs rounded mr-2 ${
                          f.type === 'NEW' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'
                        }`}>
                          {f.type}
                        </span>
                        <span className="truncate">{f.path}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* BACKLOG一覧 */}
              {dryRunResult.backlogItems && dryRunResult.backlogItems.length > 0 && (
                <div className="mt-2">
                  <p className="text-xs text-gray-500 mb-1">関連バックログ:</p>
                  <div className="flex flex-wrap gap-1">
                    {dryRunResult.backlogItems.map((b) => (
                      <span key={b.id} className="inline-block bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded">
                        {b.id}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* フッター */}
            <div className="px-6 py-4 border-t border-gray-200 flex justify-end space-x-3">
              <button
                onClick={handleCancelDialog}
                disabled={executing}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-500 focus:ring-offset-2 disabled:opacity-50"
              >
                キャンセル
              </button>
              <button
                onClick={handleConfirmRelease}
                disabled={executing}
                className="inline-flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50"
              >
                {executing ? (
                  <>
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    実行中...
                  </>
                ) : (
                  '実行'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* トースト通知 */}
      {toast && (
        <div className={`fixed bottom-4 right-4 z-50 flex items-center px-4 py-3 rounded-lg shadow-lg transition-opacity ${
          toast.type === 'success'
            ? 'bg-green-600 text-white'
            : 'bg-red-600 text-white'
        }`}>
          <svg className="w-5 h-5 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            {toast.type === 'success' ? (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            ) : (
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            )}
          </svg>
          <span className="text-sm font-medium">{toast.message}</span>
          <button
            onClick={() => setToast(null)}
            className="ml-4 text-white hover:text-gray-200"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
};
