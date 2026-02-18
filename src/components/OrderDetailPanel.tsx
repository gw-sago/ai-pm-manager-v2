import React, { useState, useEffect, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';
import type { OrderInfo, OrderResultFile } from '../preload';
import { ArtifactsBrowser } from './ArtifactsBrowser';
import { OrderReleaseSection } from './OrderReleaseSection';
import { MarkdownViewer } from './MarkdownViewer';
import { ReleaseReadinessPanel } from './ReleaseReadinessPanel';
import { useOrderActions } from '../hooks/useOrderActions';
import { useRetryOrder } from '../hooks/useRetryOrder';

interface OrderDetailPanelProps {
  /** プロジェクト名 */
  projectName: string;
  /** ORDER情報 */
  order: OrderInfo;
  /** 閉じるコールバック */
  onClose: () => void;
  /** ORDER_126 TASK_1121: タスクバッジクリック時のコールバック */
  onTaskClick?: (taskId: string) => void;
  /** ORDER_131 TASK_1136: PM実行中フラグ */
  isPmRunning?: boolean;
  /** ORDER_131 TASK_1136: Worker実行中フラグ */
  isWorkerRunning?: boolean;
  /** ORDER_131 TASK_1136: リリース実行中フラグ */
  isReleaseRunning?: boolean;
  /** ORDER_131 TASK_1136: PM実行コールバック */
  onExecutePm?: (projectId: string, orderId: string) => void;
  /** ORDER_131 TASK_1136: Worker実行コールバック */
  onExecuteWorker?: (projectId: string, orderId: string) => void;
  /** ORDER_131 TASK_1136: リリース実行コールバック */
  onExecuteRelease?: (projectId: string, orderId: string) => void;
  /** ORDER_155 TASK_1229: ORDER一覧リフレッシュコールバック */
  onRefresh?: () => void;
}

type TabType = 'order' | 'artifacts' | 'goal' | 'requirements' | 'staffing' | 'reports';

/**
 * ORDER詳細表示パネル
 *
 * ORDERをクリックした際に表示される詳細パネル。
 * タブ切り替えでORDER詳細と成果物一覧を表示する。
 *
 * TASK_192: OrderDetailPanel実装
 * TASK_194: ArtifactsBrowser統合
 * TASK_239: ORDER単位の進捗率表示を追加
 * TASK_1124: PM成果物表示タブ追加（GOAL・要件定義・STAFFING・REPORT）
 */
export const OrderDetailPanel: React.FC<OrderDetailPanelProps> = ({
  projectName,
  order,
  onClose,
  onTaskClick,
  isPmRunning = false,
  isWorkerRunning = false,
  isReleaseRunning = false,
  onExecutePm,
  onExecuteWorker,
  onExecuteRelease,
  onRefresh,
}) => {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabType>('order');

  // TASK_1124: PM成果物表示用state
  const [resultFileContent, setResultFileContent] = useState<string | null>(null);
  const [resultFileLoading, setResultFileLoading] = useState(false);
  const [resultFileError, setResultFileError] = useState<string | null>(null);

  // TASK_1124: REPORTタブ用state
  const [reportList, setReportList] = useState<string[]>([]);
  const [reportListLoading, setReportListLoading] = useState(false);
  const [selectedReport, setSelectedReport] = useState<string | null>(null);
  const [reportContent, setReportContent] = useState<string | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [reportError, setReportError] = useState<string | null>(null);

  /**
   * ORDER内タスクの進捗率を計算
   * TASK_239: 進捗率表示のORDER単位化
   */
  const getOrderProgress = () => {
    const tasks = order.tasks || [];
    const total = tasks.length;

    if (total === 0) {
      return { completed: 0, total: 0, percentage: 0, hasNoTasks: true };
    }

    const completed = tasks.filter(t => t.status === 'COMPLETED').length;
    const percentage = Math.round((completed / total) * 100);

    return { completed, total, percentage, hasNoTasks: false };
  };

  const progress = getOrderProgress();

  // ORDER_131 TASK_1137: ORDER状態判定hook（個別無効理由対応）
  const {
    canExecutePm,
    canExecuteWorker,
    canRelease,
    disabledReason,
    pmDisabledReason,
    workerDisabledReason,
    releaseDisabledReason,
  } = useOrderActions({
    order,
    isPmRunning,
    isWorkerRunning,
    isReleaseRunning,
  });

  // ORDER_155 TASK_1229: PLANNING_FAILEDリカバリhook
  const {
    isRetrying,
    retryError,
    retrySuccess,
    handleRetryOrder,
    clearRetryState,
  } = useRetryOrder({
    projectId: projectName,
    orderId: order.id,
    onSuccess: onRefresh,
  });

  // TASK_1125: ORDER変更時にPM成果物関連stateをリセット（staleデータ防止）
  useEffect(() => {
    setResultFileContent(null);
    setResultFileLoading(false);
    setResultFileError(null);
    setReportList([]);
    setReportListLoading(false);
    setSelectedReport(null);
    setReportContent(null);
    setReportLoading(false);
    setReportError(null);
    setActiveTab('order');
    clearRetryState();
  }, [order.id]);

  // ORDER詳細を取得
  const fetchOrderContent = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const orderContent = await window.electronAPI.getOrderFile(projectName, order.id);
      if (orderContent) {
        setContent(orderContent);
      } else {
        setError(`ORDER詳細ファイルが見つかりません: ${order.id}.md`);
      }
    } catch (err) {
      console.error('[OrderDetailPanel] Failed to fetch order content:', err);
      setError('ORDER詳細の取得に失敗しました');
    } finally {
      setLoading(false);
    }
  }, [projectName, order.id]);

  useEffect(() => {
    fetchOrderContent();
  }, [fetchOrderContent]);

  // DB変更イベントの購読（ORDER_004 / TASK_011）
  // スクリプト実行完了・タスクステータス変更時にORDER詳細を自動更新
  useEffect(() => {
    const unsubscribe = window.electronAPI.onDbChanged((event) => {
      // 現在表示中のプロジェクトに関係するイベントのみ再フェッチ
      if (event.projectId === projectName) {
        console.log('[OrderDetailPanel] db:changed event received:', event.source, event.targetId);
        fetchOrderContent();
      }
    });

    return () => {
      unsubscribe();
    };
  }, [projectName, fetchOrderContent]);

  /**
   * TASK_1124: RESULT配下のMarkdownファイルを取得
   */
  const fetchResultFile = useCallback(async (filename: string) => {
    setResultFileLoading(true);
    setResultFileError(null);
    setResultFileContent(null);

    try {
      const result: OrderResultFile = await window.electronAPI.getOrderResultFile(
        projectName,
        order.id,
        filename
      );
      if (result.exists && result.content) {
        setResultFileContent(result.content);
      } else {
        setResultFileError(`ファイルが見つかりません: ${filename}`);
      }
    } catch (err) {
      console.error(`[OrderDetailPanel] Failed to fetch result file ${filename}:`, err);
      setResultFileError(`${filename} の取得に失敗しました`);
    } finally {
      setResultFileLoading(false);
    }
  }, [projectName, order.id]);

  /**
   * TASK_1124: レポート一覧を取得
   * TASK_1125: selectedReportを依存配列から除外し、不要な再生成・再fetchを防止
   */
  const fetchReportList = useCallback(async () => {
    setReportListLoading(true);
    setReportError(null);

    try {
      const list = await window.electronAPI.getOrderReportList(projectName, order.id);
      setReportList(list || []);
      // 一覧取得後、最初のレポートを自動選択
      if (list && list.length > 0) {
        setSelectedReport((prev) => prev || list[0]);
      }
    } catch (err) {
      console.error('[OrderDetailPanel] Failed to fetch report list:', err);
      setReportError('レポート一覧の取得に失敗しました');
    } finally {
      setReportListLoading(false);
    }
  }, [projectName, order.id]);

  /**
   * TASK_1124: 特定レポートファイルの内容を取得
   */
  const fetchReportContent = useCallback(async (reportFilename: string) => {
    setReportLoading(true);
    setReportError(null);
    setReportContent(null);

    try {
      const result: OrderResultFile = await window.electronAPI.getOrderReport(
        projectName,
        order.id,
        reportFilename
      );
      if (result.exists && result.content) {
        setReportContent(result.content);
      } else {
        setReportError(`レポートが見つかりません: ${reportFilename}`);
      }
    } catch (err) {
      console.error(`[OrderDetailPanel] Failed to fetch report ${reportFilename}:`, err);
      setReportError(`${reportFilename} の取得に失敗しました`);
    } finally {
      setReportLoading(false);
    }
  }, [projectName, order.id]);

  // タブ切り替え時にコンテンツを取得
  useEffect(() => {
    if (activeTab === 'goal') {
      fetchResultFile('01_GOAL.md');
    } else if (activeTab === 'requirements') {
      fetchResultFile('02_REQUIREMENTS.md');
    } else if (activeTab === 'staffing') {
      fetchResultFile('03_STAFFING.md');
    } else if (activeTab === 'reports') {
      fetchReportList();
    }
  }, [activeTab, fetchResultFile, fetchReportList]);

  // 選択レポート変更時にコンテンツを取得
  useEffect(() => {
    if (activeTab === 'reports' && selectedReport) {
      fetchReportContent(selectedReport);
    }
  }, [activeTab, selectedReport, fetchReportContent]);

  /**
   * ステータスに応じたバッジの色を取得
   */
  const getStatusBadgeColor = (status: string): string => {
    switch (status.toUpperCase()) {
      case 'COMPLETED':
        return 'bg-green-100 text-green-800';
      case 'IN_PROGRESS':
        return 'bg-blue-100 text-blue-800';
      case 'REVIEW':
      case 'IN_REVIEW':
        return 'bg-yellow-100 text-yellow-800';
      case 'REWORK':
        return 'bg-red-100 text-red-800';
      case 'PLANNING':
        return 'bg-purple-100 text-purple-800';
      case 'PLANNING_FAILED':
        return 'bg-red-100 text-red-800';
      case 'CANCELLED':
        return 'bg-gray-200 text-gray-600';
      case 'REJECTED':
        return 'bg-red-200 text-red-900';
      case 'ON_HOLD':
        return 'bg-yellow-200 text-yellow-800';
      default:
        return 'bg-gray-100 text-gray-800';
    }
  };

  /**
   * タブボタンのスタイルを取得
   */
  const getTabStyle = (tab: TabType): string => {
    const baseStyle = 'px-3 py-2 text-sm font-medium border-b-2 transition-colors whitespace-nowrap';
    if (activeTab === tab) {
      return `${baseStyle} border-blue-500 text-blue-600`;
    }
    return `${baseStyle} border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300`;
  };

  /**
   * TASK_1124: ローディングスピナー共通コンポーネント
   */
  const LoadingSpinner: React.FC = () => (
    <div className="flex items-center justify-center h-32">
      <svg
        className="animate-spin h-6 w-6 text-blue-500"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
        />
      </svg>
      <span className="ml-2 text-sm text-gray-500">読み込み中...</span>
    </div>
  );

  /**
   * TASK_1124: エラー表示共通コンポーネント
   */
  const ErrorDisplay: React.FC<{ message: string }> = ({ message }) => (
    <div className="flex flex-col items-center justify-center h-32 text-center">
      <svg
        className="w-8 h-8 text-gray-400 mb-2"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
        />
      </svg>
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  );

  /**
   * TASK_1124: 「ファイルなし」表示共通コンポーネント
   */
  const NoContentDisplay: React.FC<{ title: string; description: string }> = ({ title, description }) => (
    <div className="flex flex-col items-center justify-center h-32 text-center">
      <svg
        className="w-12 h-12 text-gray-300 mb-3"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={1.5}
          d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
        />
      </svg>
      <h3 className="text-base font-medium text-gray-600 mb-1">{title}</h3>
      <p className="text-sm text-gray-400">{description}</p>
    </div>
  );

  /**
   * TASK_1124: RESULT Markdownファイル表示用コンテンツ（GOAL/要件定義/STAFFING共通）
   */
  const renderResultFileContent = () => {
    if (resultFileLoading) {
      return <LoadingSpinner />;
    }
    if (resultFileError) {
      return <ErrorDisplay message={resultFileError} />;
    }
    if (resultFileContent) {
      return <MarkdownViewer content={resultFileContent} />;
    }
    return null;
  };

  /**
   * TASK_1124: REPORTタブコンテンツ
   */
  const renderReportsContent = () => {
    if (reportListLoading) {
      return <LoadingSpinner />;
    }

    if (reportError && reportList.length === 0) {
      return <ErrorDisplay message={reportError} />;
    }

    if (reportList.length === 0) {
      return (
        <NoContentDisplay
          title="レポートなし"
          description="このORDERにはまだレポートファイルが作成されていません。タスク完了後にレポートが生成されます。"
        />
      );
    }

    return (
      <div className="flex flex-col h-full">
        {/* レポート選択セレクタ */}
        <div className="flex items-center space-x-2 mb-3 px-1">
          <label className="text-xs font-medium text-gray-500 whitespace-nowrap">
            REPORT:
          </label>
          <select
            value={selectedReport || ''}
            onChange={(e) => setSelectedReport(e.target.value)}
            className="flex-1 text-sm border border-gray-300 rounded px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
          >
            {reportList.map((filename) => (
              <option key={filename} value={filename}>
                {filename}
              </option>
            ))}
          </select>
          <span className="text-xs text-gray-400">
            {reportList.length}件
          </span>
        </div>

        {/* レポート内容 */}
        <div className="flex-1 overflow-auto">
          {reportLoading ? (
            <LoadingSpinner />
          ) : reportError ? (
            <ErrorDisplay message={reportError} />
          ) : reportContent ? (
            <MarkdownViewer content={reportContent} />
          ) : null}
        </div>
      </div>
    );
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 flex flex-col h-full">
      {/* ヘッダー */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200">
        <div className="flex items-center space-x-3">
          <h2 className="text-lg font-semibold text-gray-900">
            {order.id}
          </h2>
          {order.title && (
            <span className="text-gray-600">: {order.title}</span>
          )}
          <span
            className={`px-2 py-0.5 text-xs font-medium rounded-full ${getStatusBadgeColor(order.status)}`}
          >
            {order.status}
          </span>
          {/* TASK_239: ORDER進捗率表示 */}
          <span className="text-sm text-gray-500 ml-2">
            {progress.hasNoTasks ? (
              <span className="text-gray-400">タスクなし</span>
            ) : (
              <span className={progress.percentage === 100 ? 'text-green-600 font-medium' : ''}>
                {progress.completed}/{progress.total} タスク完了 ({progress.percentage}%)
              </span>
            )}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 hover:bg-gray-100 rounded-md transition-colors"
          title="閉じる"
        >
          <svg
            className="w-5 h-5 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      {/* ORDER_131 TASK_1138: アクションバー */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          {/* ステータス表示 */}
          <div className="text-sm text-gray-600">
            {disabledReason}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {/* PLANNING時: PM実行中の進捗表示のみ（ボタンはバックログリストから実行） */}
          {order.status === 'PLANNING' && isPmRunning && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium bg-blue-100 text-blue-600">
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span>PM実行中...</span>
            </div>
          )}
          {/* Worker実行ボタン（IN_PROGRESS時、未完了タスクあり） */}
          {order.status === 'IN_PROGRESS' && progress.completed < progress.total && (
            <button
              onClick={() => onExecuteWorker?.(projectName, order.id)}
              disabled={!canExecuteWorker}
              title={canExecuteWorker ? 'Worker処理を並列実行' : workerDisabledReason}
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors
                ${isWorkerRunning
                  ? 'bg-blue-100 text-blue-600 cursor-wait'
                  : canExecuteWorker
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                }
              `}
            >
              {isWorkerRunning ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>Worker実行中...</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  <span>Worker実行</span>
                </>
              )}
            </button>
          )}
          {/* TASK_1150: リリースボタンは成果物タブのReleaseReadinessPanelに移設 */}
          {order.status === 'IN_PROGRESS' && progress.completed === progress.total && progress.total > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm bg-blue-50 text-blue-700">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>リリース準備完了 - 成果物タブを確認</span>
            </div>
          )}
          {/* COMPLETED時のバッジ表示 */}
          {order.status === 'COMPLETED' && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium bg-green-100 text-green-700">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span>リリース済み</span>
            </div>
          )}
          {/* ORDER_155 TASK_1229: PLANNING_FAILED時のリカバリボタン */}
          {order.status === 'PLANNING_FAILED' && (
            <div className="flex items-center gap-2">
              {retrySuccess && (
                <span className="text-sm text-green-600 font-medium">
                  再実行完了
                </span>
              )}
              {retryError && (
                <span className="text-sm text-red-600 max-w-xs truncate" title={retryError}>
                  {retryError}
                </span>
              )}
              <button
                onClick={handleRetryOrder}
                disabled={isRetrying}
                title={isRetrying ? 'PM処理を再実行中...' : 'PLANNING_FAILEDのORDERを再実行します'}
                className={`
                  flex items-center gap-1.5 px-3 py-1.5 rounded text-sm font-medium transition-colors
                  ${isRetrying
                    ? 'bg-orange-100 text-orange-600 cursor-wait'
                    : 'bg-orange-600 text-white hover:bg-orange-700'
                  }
                `}
              >
                {isRetrying ? (
                  <>
                    <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>PM処理を再実行中...</span>
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    <span>PM処理を再実行</span>
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* タブナビゲーション - TASK_1124: PM成果物タブ追加 */}
      <div className="flex border-b border-gray-200 px-4 overflow-x-auto">
        <button
          onClick={() => setActiveTab('order')}
          className={getTabStyle('order')}
        >
          <span className="flex items-center">
            <svg
              className="w-4 h-4 mr-1.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            ORDER詳細
          </span>
        </button>
        <button
          onClick={() => setActiveTab('goal')}
          className={getTabStyle('goal')}
        >
          <span className="flex items-center">
            <svg
              className="w-4 h-4 mr-1.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
            GOAL
          </span>
        </button>
        <button
          onClick={() => setActiveTab('requirements')}
          className={getTabStyle('requirements')}
        >
          <span className="flex items-center">
            <svg
              className="w-4 h-4 mr-1.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"
              />
            </svg>
            要件定義
          </span>
        </button>
        <button
          onClick={() => setActiveTab('staffing')}
          className={getTabStyle('staffing')}
        >
          <span className="flex items-center">
            <svg
              className="w-4 h-4 mr-1.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            STAFFING
          </span>
        </button>
        <button
          onClick={() => setActiveTab('reports')}
          className={getTabStyle('reports')}
        >
          <span className="flex items-center">
            <svg
              className="w-4 h-4 mr-1.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            REPORT
          </span>
        </button>
        <button
          onClick={() => setActiveTab('artifacts')}
          className={getTabStyle('artifacts')}
        >
          <span className="flex items-center">
            <svg
              className="w-4 h-4 mr-1.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
              />
            </svg>
            成果物
          </span>
        </button>
      </div>

      {/* コンテンツエリア */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'order' && (
          <div className="h-full overflow-auto p-4">
            {loading && <LoadingSpinner />}

            {error && <ErrorDisplay message={error} />}

            {/* ORDER_108/TASK_995: リリース情報セクション */}
            <OrderReleaseSection
              projectId={projectName}
              orderId={order.id}
              tasks={order.tasks}
            />

            {!loading && !error && content && (
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown
                  components={{
                    h1: ({ children }) => (
                      <h1 className="text-xl font-bold text-gray-900 mt-4 mb-2 first:mt-0">
                        {children}
                      </h1>
                    ),
                    h2: ({ children }) => (
                      <h2 className="text-lg font-semibold text-gray-800 mt-4 mb-2 border-b border-gray-200 pb-1">
                        {children}
                      </h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="text-base font-semibold text-gray-700 mt-3 mb-1">
                        {children}
                      </h3>
                    ),
                    p: ({ children }) => (
                      <p className="text-sm text-gray-600 my-2">{children}</p>
                    ),
                    ul: ({ children }) => (
                      <ul className="list-disc list-inside text-sm text-gray-600 my-2 space-y-1">
                        {children}
                      </ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="list-decimal list-inside text-sm text-gray-600 my-2 space-y-1">
                        {children}
                      </ol>
                    ),
                    li: ({ children }) => (
                      <li className="text-sm text-gray-600">{children}</li>
                    ),
                    code: ({ children, className }) => {
                      const isInline = !className;
                      return isInline ? (
                        <code className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-xs font-mono">
                          {children}
                        </code>
                      ) : (
                        <code className="block bg-gray-50 text-gray-800 p-3 rounded-md text-xs font-mono overflow-x-auto">
                          {children}
                        </code>
                      );
                    },
                    pre: ({ children }) => (
                      <pre className="bg-gray-50 p-3 rounded-md overflow-x-auto my-2">
                        {children}
                      </pre>
                    ),
                    table: ({ children }) => (
                      <div className="overflow-x-auto my-2">
                        <table className="min-w-full text-sm border-collapse border border-gray-200">
                          {children}
                        </table>
                      </div>
                    ),
                    th: ({ children }) => (
                      <th className="border border-gray-200 bg-gray-50 px-3 py-1.5 text-left font-medium text-gray-700">
                        {children}
                      </th>
                    ),
                    td: ({ children }) => (
                      <td className="border border-gray-200 px-3 py-1.5 text-gray-600">
                        {children}
                      </td>
                    ),
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-4 border-gray-300 pl-3 my-2 text-sm text-gray-600 italic">
                        {children}
                      </blockquote>
                    ),
                    a: ({ href, children }) => (
                      <a
                        href={href}
                        className="text-blue-600 hover:underline"
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {children}
                      </a>
                    ),
                    hr: () => <hr className="my-4 border-gray-200" />,
                  }}
                >
                  {content}
                </ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {/* TASK_1124: GOAL表示タブ */}
        {activeTab === 'goal' && (
          <div className="h-full overflow-auto p-4">
            {renderResultFileContent()}
          </div>
        )}

        {/* TASK_1124: 要件定義表示タブ */}
        {activeTab === 'requirements' && (
          <div className="h-full overflow-auto p-4">
            {renderResultFileContent()}
          </div>
        )}

        {/* TASK_1124: STAFFING表示タブ */}
        {activeTab === 'staffing' && (
          <div className="h-full overflow-auto p-4">
            {renderResultFileContent()}
          </div>
        )}

        {/* TASK_1124: REPORTタブ */}
        {activeTab === 'reports' && (
          <div className="h-full overflow-auto p-4">
            {renderReportsContent()}
          </div>
        )}

        {activeTab === 'artifacts' && (
          <div className="h-full overflow-auto p-4">
            {/* TASK_1150: ReleaseReadinessPanel統合 - リリース判定情報を成果物タブに表示 */}
            <ReleaseReadinessPanel
              projectName={projectName}
              orderId={order.id}
              tasks={order.tasks}
              onExecuteRelease={() => onExecuteRelease?.(projectName, order.id)}
              isReleaseRunning={isReleaseRunning}
            />
            {/* 既存のArtifactsBrowser */}
            <div className="mt-6 border-t border-gray-200 pt-6">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">成果物ファイル一覧</h3>
              <ArtifactsBrowser projectName={projectName} orderId={order.id} />
            </div>
          </div>
        )}
      </div>

      {/* フッター: タスク情報 - TASK_239: 進捗率表示改善 */}
      <div className="border-t border-gray-200 p-4">
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          {progress.hasNoTasks ? (
            'タスク一覧'
          ) : (
            <>タスク一覧 ({progress.completed}/{progress.total} 完了 - {progress.percentage}%)</>
          )}
        </h4>
        {progress.hasNoTasks ? (
          <div className="text-sm text-gray-400 py-2">
            このORDERにはタスクがありません
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {order.tasks.map((task) => {
              const taskStatusStyle: Record<string, { badge: string; dot: string }> = {
                COMPLETED: { badge: 'bg-green-50 text-green-700', dot: 'bg-green-500' },
                IN_PROGRESS: { badge: 'bg-blue-50 text-blue-700', dot: 'bg-blue-500' },
                REWORK: { badge: 'bg-red-50 text-red-700', dot: 'bg-red-500' },
                IN_REVIEW: { badge: 'bg-orange-50 text-orange-700', dot: 'bg-orange-500' },
                DONE: { badge: 'bg-yellow-50 text-yellow-700', dot: 'bg-yellow-500' },
                BLOCKED: { badge: 'bg-red-50 text-red-600', dot: 'bg-red-400' },
                CANCELLED: { badge: 'bg-gray-100 text-gray-500', dot: 'bg-gray-400' },
                REJECTED: { badge: 'bg-red-100 text-red-800', dot: 'bg-red-600' },
                SKIPPED: { badge: 'bg-gray-50 text-gray-400', dot: 'bg-gray-300' },
              };
              const style = taskStatusStyle[task.status] || { badge: 'bg-gray-50 text-gray-600', dot: 'bg-gray-400' };
              return (
                <button
                  key={task.id}
                  className={`inline-flex items-center px-2 py-0.5 rounded text-xs cursor-pointer hover:opacity-80 hover:shadow-sm transition-all ${style.badge}`}
                  title={task.title || task.id}
                  onClick={() => onTaskClick?.(task.id)}
                >
                  <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${style.dot}`} />
                  {task.id.replace('TASK_', '')}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
