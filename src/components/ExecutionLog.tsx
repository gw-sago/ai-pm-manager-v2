/**
 * ExecutionLog Component
 *
 * ワンクリック実行（PM/Worker）の実行ログを表示するコンポーネント
 *
 * ORDER_040: ワンクリック実行ログ機能（実行ログタブ）
 * TASK_573: ExecutionLogコンポーネント実装
 * ORDER_111 / TASK_1002: バックグラウンドWorkerログタブ追加
 */

import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import type {
  ExecutionResult,
  ExecutionProgress,
  RunningJob,
  WorkerLogFileInfo,
  WorkerLogContent,
  WorkerLogUpdateEvent,
} from '../preload';

// =============================================================================
// 型定義
// =============================================================================

interface ExecutionLogProps {
  /** 最大表示件数（デフォルト: 50） */
  maxItems?: number;
  /** リフレッシュ間隔（ミリ秒、デフォルト: 5000） */
  refreshInterval?: number;
  /** プロジェクトID（バックグラウンドログ取得に必要） */
  projectId?: string;
}

/** 内部タブ: フォアグラウンド / バックグラウンド */
type LogTabType = 'foreground' | 'background';

// =============================================================================
// 定数
// =============================================================================

/** ステータスに対応する色クラス */
const STATUS_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  running: {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
  },
  completed: {
    bg: 'bg-green-50',
    text: 'text-green-700',
    border: 'border-green-200',
  },
  failed: {
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
  },
};

/** タイプに対応するラベル */
const TYPE_LABELS: Record<string, string> = {
  pm: 'PM',
  worker: 'Worker',
};

/** Worker ログステータスのバッジ色 */
const WORKER_LOG_STATUS_STYLES: Record<string, { bg: string; text: string; dot?: string }> = {
  running: { bg: 'bg-blue-100', text: 'text-blue-700', dot: 'bg-blue-500' },
  success: { bg: 'bg-green-100', text: 'text-green-700' },
  failed: { bg: 'bg-red-100', text: 'text-red-700' },
  unknown: { bg: 'bg-gray-100', text: 'text-gray-600' },
};

/** Worker ログステータスの日本語ラベル */
const WORKER_LOG_STATUS_LABELS: Record<string, string> = {
  running: '実行中',
  success: '成功',
  failed: '失敗',
  unknown: '不明',
};

/** ログ行のレベル色マッピング */
const WORKER_LOG_LEVEL_COLORS: Record<string, string> = {
  '[ERROR]': 'text-red-400',
  'ERROR': 'text-red-400',
  '[WARN]': 'text-yellow-400',
  'WARNING': 'text-yellow-400',
  '[INFO]': 'text-blue-400',
  'INFO': 'text-blue-400',
  '[DEBUG]': 'text-gray-500',
  'DEBUG': 'text-gray-500',
};

// =============================================================================
// メインコンポーネント
// =============================================================================

export const ExecutionLog: React.FC<ExecutionLogProps> = ({
  maxItems = 50,
  refreshInterval = 5000,
  projectId,
}) => {
  // タブ切り替え
  const [activeLogTab, setActiveLogTab] = useState<LogTabType>('foreground');

  // ===== フォアグラウンドタブ用 状態管理 =====
  const [history, setHistory] = useState<ExecutionResult[]>([]);
  const [runningJobs, setRunningJobs] = useState<RunningJob[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // データ取得
  const fetchData = useCallback(async () => {
    try {
      const [historyData, runningData] = await Promise.all([
        window.electronAPI.getExecutionHistory(),
        window.electronAPI.getRunningJobs(),
      ]);
      setHistory(historyData.slice(0, maxItems));
      setRunningJobs(runningData);
    } catch (err) {
      console.error('[ExecutionLog] Failed to fetch data:', err);
    } finally {
      setIsLoading(false);
    }
  }, [maxItems]);

  // 初回読み込み
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 定期リフレッシュ
  useEffect(() => {
    const interval = setInterval(fetchData, refreshInterval);
    return () => clearInterval(interval);
  }, [fetchData, refreshInterval]);

  // 実行完了イベントのリスナー
  useEffect(() => {
    const unsubscribe = window.electronAPI.onExecutionComplete(() => {
      fetchData();
    });
    return () => unsubscribe();
  }, [fetchData]);

  // 進捗イベントのリスナー
  useEffect(() => {
    const unsubscribe = window.electronAPI.onExecutionProgress(() => {
      fetchData();
    });
    return () => unsubscribe();
  }, [fetchData]);

  // 詳細展開トグル
  const handleToggleExpand = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  // 履歴クリア
  const handleClearHistory = useCallback(async () => {
    try {
      await window.electronAPI.clearExecutionHistory();
      setHistory([]);
    } catch (err) {
      console.error('[ExecutionLog] Failed to clear history:', err);
    }
  }, []);

  // ローディング表示（フォアグラウンドタブのみ）
  if (isLoading && activeLogTab === 'foreground') {
    return (
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-8">
        <div className="flex items-center justify-center">
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
          <span className="ml-2 text-sm text-gray-500">読み込み中...</span>
        </div>
      </div>
    );
  }

  // 実行中ジョブと履歴を結合（実行中を先頭に）
  const allItems: (RunningJob | ExecutionResult)[] = [
    ...runningJobs.map((job) => ({ ...job, isRunning: true })),
    ...history,
  ];

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
      {/* ヘッダー */}
      <div className="flex items-center justify-between p-4 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-gray-800">実行ログ</h3>
          {activeLogTab === 'foreground' && (
            <span className="text-xs text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
              {runningJobs.length > 0 && (
                <span className="text-blue-600 mr-1">{runningJobs.length} 実行中</span>
              )}
              {history.length} 件
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {activeLogTab === 'foreground' && (
            <>
              {/* リフレッシュボタン */}
              <button
                onClick={fetchData}
                className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
                title="更新"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              </button>
              {/* クリアボタン */}
              {history.length > 0 && (
                <button
                  onClick={handleClearHistory}
                  className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
                  title="履歴をクリア"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* タブ切り替え */}
      <div className="flex border-b border-gray-200 px-4">
        <button
          onClick={() => setActiveLogTab('foreground')}
          className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
            activeLogTab === 'foreground'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          }`}
        >
          フォアグラウンド
        </button>
        <button
          onClick={() => setActiveLogTab('background')}
          className={`px-3 py-2 text-xs font-medium border-b-2 transition-colors ${
            activeLogTab === 'background'
              ? 'border-blue-500 text-blue-600'
              : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
          }`}
        >
          バックグラウンド
        </button>
      </div>

      {/* コンテンツ */}
      {activeLogTab === 'foreground' ? (
        <div className="p-4">
          {/* 空状態 */}
          {allItems.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                  />
                </svg>
              </div>
              <p className="text-sm text-gray-500 mb-1">実行ログがありません</p>
              <p className="text-xs text-gray-400">
                バックログからPM/Worker実行を開始すると、ここにログが表示されます
              </p>
            </div>
          )}

          {/* ログリスト */}
          {allItems.length > 0 && (
            <div className="space-y-2">
              {allItems.map((item) => {
                const isRunning = 'isRunning' in item;
                const id = isRunning ? (item as RunningJob).executionId : (item as ExecutionResult).executionId;
                const status = isRunning ? 'running' : (item as ExecutionResult).success ? 'completed' : 'failed';

                return (
                  <ExecutionLogItem
                    key={id}
                    item={item}
                    status={status}
                    isExpanded={expandedId === id}
                    onToggleExpand={() => handleToggleExpand(id)}
                  />
                );
              })}
            </div>
          )}
        </div>
      ) : (
        <BackgroundLogTab projectId={projectId || ''} />
      )}
    </div>
  );
};

// =============================================================================
// バックグラウンドログタブ
// =============================================================================

interface BackgroundLogTabProps {
  projectId: string;
}

const BackgroundLogTab: React.FC<BackgroundLogTabProps> = ({ projectId }) => {
  const [logFiles, setLogFiles] = useState<WorkerLogFileInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedLog, setSelectedLog] = useState<WorkerLogFileInfo | null>(null);
  const [filterOrderId, setFilterOrderId] = useState<string>('');
  const [filterTaskId, setFilterTaskId] = useState<string>('');

  // ログ一覧取得
  const fetchLogFiles = useCallback(async () => {
    if (!projectId) {
      setIsLoading(false);
      return;
    }
    try {
      const logs = await window.electronAPI.getWorkerLogs(projectId);
      setLogFiles(logs);
    } catch (err) {
      console.error('[BackgroundLogTab] Failed to fetch worker logs:', err);
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  // 初回読み込み
  useEffect(() => {
    fetchLogFiles();
  }, [fetchLogFiles]);

  // 10秒ごとの自動リフレッシュ（一覧表示中のみ）
  useEffect(() => {
    if (selectedLog) return; // ログ内容表示中はリフレッシュ不要
    const interval = setInterval(fetchLogFiles, 10000);
    return () => clearInterval(interval);
  }, [fetchLogFiles, selectedLog]);

  // ユニークなORDER IDリスト
  const uniqueOrderIds = useMemo(() => {
    const ids = new Set(logFiles.map((f) => f.orderId));
    return Array.from(ids).sort();
  }, [logFiles]);

  // ユニークなTask IDリスト
  const uniqueTaskIds = useMemo(() => {
    const ids = new Set(logFiles.map((f) => f.taskId));
    return Array.from(ids).sort();
  }, [logFiles]);

  // フィルタリング
  const filteredLogs = useMemo(() => {
    return logFiles.filter((log) => {
      if (filterOrderId && log.orderId !== filterOrderId) return false;
      if (filterTaskId && log.taskId !== filterTaskId) return false;
      return true;
    });
  }, [logFiles, filterOrderId, filterTaskId]);

  // ログ内容表示から一覧に戻る
  const handleBackToList = useCallback(() => {
    setSelectedLog(null);
  }, []);

  if (!projectId) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-center p-4">
        <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-4">
          <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <p className="text-sm text-gray-500">プロジェクトが選択されていません</p>
        <p className="text-xs text-gray-400 mt-1">
          プロジェクトを選択すると、バックグラウンドWorkerのログが表示されます
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
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
        <span className="ml-2 text-sm text-gray-500">Workerログを読み込み中...</span>
      </div>
    );
  }

  // ログ内容表示モード
  if (selectedLog) {
    return (
      <WorkerLogContentViewer
        logFile={selectedLog}
        onBack={handleBackToList}
      />
    );
  }

  // 一覧表示モード
  return (
    <div className="p-4">
      {/* フィルタバー */}
      <div className="flex items-center gap-3 mb-3">
        <select
          value={filterOrderId}
          onChange={(e) => setFilterOrderId(e.target.value)}
          className="text-xs border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="">全ORDER</option>
          {uniqueOrderIds.map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
        <select
          value={filterTaskId}
          onChange={(e) => setFilterTaskId(e.target.value)}
          className="text-xs border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="">全Task</option>
          {uniqueTaskIds.map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
        <button
          onClick={fetchLogFiles}
          className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors ml-auto"
          title="更新"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
        <span className="text-xs text-gray-400">{filteredLogs.length} 件</span>
      </div>

      {/* ログファイル一覧 */}
      {filteredLogs.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-4">
            <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          </div>
          <p className="text-sm text-gray-500 mb-1">Workerログがありません</p>
          <p className="text-xs text-gray-400">
            Worker実行を開始すると、バックグラウンドログがここに表示されます
          </p>
        </div>
      ) : (
        <div className="space-y-1">
          {/* テーブルヘッダ */}
          <div className="grid grid-cols-[80px_100px_80px_70px_140px] gap-2 px-3 py-1.5 text-xs font-medium text-gray-500 border-b border-gray-200">
            <span>ORDER</span>
            <span>Task ID</span>
            <span>Status</span>
            <span>Size</span>
            <span>更新日時</span>
          </div>
          {/* テーブルボディ */}
          {filteredLogs.map((log) => (
            <WorkerLogFileRow
              key={log.filePath}
              log={log}
              onClick={() => setSelectedLog(log)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// =============================================================================
// Worker ログファイル行
// =============================================================================

interface WorkerLogFileRowProps {
  log: WorkerLogFileInfo;
  onClick: () => void;
}

const WorkerLogFileRow: React.FC<WorkerLogFileRowProps> = ({ log, onClick }) => {
  const statusStyle = WORKER_LOG_STATUS_STYLES[log.status] || WORKER_LOG_STATUS_STYLES.unknown;
  const statusLabel = WORKER_LOG_STATUS_LABELS[log.status] || log.status;

  return (
    <button
      onClick={onClick}
      className="w-full grid grid-cols-[80px_100px_80px_70px_140px] gap-2 px-3 py-2 text-xs text-left hover:bg-gray-50 rounded-md transition-colors border border-transparent hover:border-gray-200"
    >
      <span className="text-gray-700 font-mono truncate" title={log.orderId}>
        {log.orderId}
      </span>
      <span className="text-gray-700 font-mono truncate" title={log.taskId}>
        {log.taskId}
      </span>
      <span>
        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium ${statusStyle.bg} ${statusStyle.text}`}>
          {log.status === 'running' && (
            <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${statusStyle.dot}`} />
          )}
          {statusLabel}
        </span>
      </span>
      <span className="text-gray-500">{formatFileSize(log.fileSize)}</span>
      <span className="text-gray-500">{formatDateTime(log.modifiedAt)}</span>
    </button>
  );
};

// =============================================================================
// Worker ログ内容ビューア
// =============================================================================

interface WorkerLogContentViewerProps {
  logFile: WorkerLogFileInfo;
  onBack: () => void;
}

const WorkerLogContentViewer: React.FC<WorkerLogContentViewerProps> = ({
  logFile,
  onBack,
}) => {
  const [content, setContent] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [isFollowing, setIsFollowing] = useState(logFile.status === 'running');
  const [error, setError] = useState<string | null>(null);
  const logContainerRef = useRef<HTMLPreElement>(null);
  const readPositionRef = useRef<number>(0);
  const watchedFileRef = useRef<string | null>(null);

  // ログ内容の初回読み込み
  const loadContent = useCallback(async () => {
    try {
      setIsLoading(true);
      const result = await window.electronAPI.readWorkerLog(logFile.filePath, { tailLines: 500 });
      if (result) {
        setContent(result.content);
        readPositionRef.current = result.readPosition;
        setError(null);
      } else {
        setError('ログファイルの読み込みに失敗しました');
      }
    } catch (err) {
      console.error('[WorkerLogContentViewer] Failed to load content:', err);
      setError('ログファイルの読み込みに失敗しました');
    } finally {
      setIsLoading(false);
    }
  }, [logFile.filePath]);

  // 初回読み込み
  useEffect(() => {
    loadContent();
  }, [loadContent]);

  // 自動スクロール
  const scrollToBottom = useCallback(() => {
    if (logContainerRef.current && isFollowing) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [isFollowing]);

  // 内容更新時のスクロール
  useEffect(() => {
    scrollToBottom();
  }, [content, scrollToBottom]);

  // running状態のログを監視
  useEffect(() => {
    if (logFile.status !== 'running') return;

    const filePath = logFile.filePath;

    // watchを開始
    window.electronAPI.watchWorkerLog(filePath).then(() => {
      watchedFileRef.current = filePath;
      console.log('[WorkerLogContentViewer] Started watching:', filePath);
    }).catch((err) => {
      console.error('[WorkerLogContentViewer] Failed to watch:', err);
    });

    return () => {
      // クリーンアップ: watchを停止
      if (watchedFileRef.current) {
        window.electronAPI.unwatchWorkerLog(watchedFileRef.current).then(() => {
          console.log('[WorkerLogContentViewer] Stopped watching:', watchedFileRef.current);
          watchedFileRef.current = null;
        }).catch((err) => {
          console.error('[WorkerLogContentViewer] Failed to unwatch:', err);
        });
      }
    };
  }, [logFile.filePath, logFile.status]);

  // ログ更新イベントのリスナー
  useEffect(() => {
    const unsubscribe = window.electronAPI.onWorkerLogUpdate((data: WorkerLogUpdateEvent) => {
      if (data.filePath === logFile.filePath && data.appendedContent) {
        setContent((prev) => prev + data.appendedContent);
        readPositionRef.current = data.readPosition;
      }
    });
    return () => unsubscribe();
  }, [logFile.filePath]);

  // コンポーネントのアンマウント時にwatchを停止
  useEffect(() => {
    return () => {
      if (watchedFileRef.current) {
        window.electronAPI.unwatchWorkerLog(watchedFileRef.current).catch(() => {
          // ignore
        });
        watchedFileRef.current = null;
      }
    };
  }, []);

  const statusStyle = WORKER_LOG_STATUS_STYLES[logFile.status] || WORKER_LOG_STATUS_STYLES.unknown;
  const statusLabel = WORKER_LOG_STATUS_LABELS[logFile.status] || logFile.status;

  return (
    <div className="flex flex-col" style={{ maxHeight: '600px' }}>
      {/* ヘッダーバー */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 bg-gray-50 flex-shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="flex items-center gap-1 text-xs text-gray-600 hover:text-blue-600 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            一覧に戻る
          </button>
          <span className="text-xs text-gray-400">|</span>
          <span className="text-xs font-mono text-gray-700">{logFile.orderId} / {logFile.taskId}</span>
          <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium ${statusStyle.bg} ${statusStyle.text}`}>
            {logFile.status === 'running' && (
              <span className={`w-1.5 h-1.5 rounded-full animate-pulse ${statusStyle.dot}`} />
            )}
            {statusLabel}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* フォロートグル */}
          <button
            onClick={() => setIsFollowing((prev) => !prev)}
            className={`flex items-center gap-1 px-2 py-1 text-xs rounded-md transition-colors ${
              isFollowing
                ? 'bg-blue-100 text-blue-700'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
            title={isFollowing ? 'フォロー中（自動スクロール）' : 'フォロー停止'}
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
            Follow
          </button>
          {/* リフレッシュボタン */}
          <button
            onClick={loadContent}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            title="再読み込み"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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

      {/* エラー表示 */}
      {error && (
        <div className="px-4 py-2 bg-red-50 border-b border-red-200 flex-shrink-0">
          <div className="flex items-center gap-2 text-xs text-red-700">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {error}
          </div>
        </div>
      )}

      {/* ログ内容 */}
      {isLoading ? (
        <div className="flex items-center justify-center p-8">
          <svg
            className="animate-spin h-5 w-5 text-blue-500"
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
          <span className="ml-2 text-sm text-gray-500">ログを読み込み中...</span>
        </div>
      ) : (
        <pre
          ref={logContainerRef}
          className="flex-1 overflow-auto bg-gray-900 text-gray-100 text-xs p-4 font-mono whitespace-pre-wrap"
          style={{ minHeight: '200px', maxHeight: '500px' }}
          onScroll={(e) => {
            const target = e.currentTarget;
            const isAtBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + 50;
            if (!isAtBottom && isFollowing) {
              setIsFollowing(false);
            }
          }}
        >
          {content ? (
            <WorkerLogContentRenderer content={content} />
          ) : (
            <span className="text-gray-500">ログ内容がありません</span>
          )}
        </pre>
      )}

      {/* フッター */}
      <div className="flex items-center justify-between px-4 py-1.5 border-t border-gray-200 bg-gray-50 text-xs text-gray-500 flex-shrink-0">
        <span className="font-mono truncate" title={logFile.fileName}>{logFile.fileName}</span>
        <span>{formatFileSize(logFile.fileSize)}</span>
      </div>
    </div>
  );
};

// =============================================================================
// Worker ログ内容レンダラー
// =============================================================================

interface WorkerLogContentRendererProps {
  content: string;
}

const WorkerLogContentRenderer: React.FC<WorkerLogContentRendererProps> = ({ content }) => {
  const lines = content.split('\n');

  return (
    <>
      {lines.map((line, index) => (
        <WorkerLogLine key={index} line={line} />
      ))}
    </>
  );
};

interface WorkerLogLineProps {
  line: string;
}

const WorkerLogLine: React.FC<WorkerLogLineProps> = React.memo(({ line }) => {
  // ログレベルを検出
  let colorClass = 'text-gray-100';

  // 優先度順に判定（ERRORを最優先）
  if (line.includes('[ERROR]') || line.includes('ERROR')) {
    colorClass = 'text-red-400';
  } else if (line.includes('[WARN]') || line.includes('WARNING')) {
    colorClass = 'text-yellow-400';
  } else if (line.includes('[DEBUG]') || line.includes('DEBUG')) {
    colorClass = 'text-gray-500';
  } else if (line.includes('[INFO]') || line.includes('INFO')) {
    colorClass = 'text-blue-400';
  }

  // 区切り線を検出
  if (line.includes('=====') || line.includes('-----')) {
    colorClass = 'text-gray-500';
  }

  return <div className={colorClass}>{line || ' '}</div>;
});

WorkerLogLine.displayName = 'WorkerLogLine';

// =============================================================================
// フォアグラウンドログ サブコンポーネント（既存）
// =============================================================================

interface ExecutionLogItemProps {
  item: RunningJob | ExecutionResult;
  status: 'running' | 'completed' | 'failed';
  isExpanded: boolean;
  onToggleExpand: () => void;
}

const ExecutionLogItem: React.FC<ExecutionLogItemProps> = ({
  item,
  status,
  isExpanded,
  onToggleExpand,
}) => {
  const colors = STATUS_COLORS[status];
  const isRunning = status === 'running';
  const result = !isRunning ? (item as ExecutionResult) : null;
  const runningJob = isRunning ? (item as RunningJob) : null;

  const type = result?.type || runningJob?.type || 'pm';
  const projectId = result?.projectId || runningJob?.projectId || '';
  const targetId = result?.targetId || runningJob?.targetId || '';
  const startedAt = result?.startedAt || runningJob?.startedAt || '';

  return (
    <div className={`rounded-lg border ${colors.border} ${colors.bg} overflow-hidden`}>
      {/* ヘッダー行 */}
      <button
        onClick={onToggleExpand}
        className="w-full flex items-center justify-between p-3 hover:bg-white/50 transition-colors text-left"
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {/* ステータスアイコン */}
          <div className="flex-shrink-0">
            {isRunning ? (
              <svg className="w-5 h-5 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            ) : status === 'completed' ? (
              <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
          </div>

          {/* タイプバッジ */}
          <span className={`flex-shrink-0 px-2 py-0.5 text-xs font-medium rounded ${colors.text} bg-white/50`}>
            {TYPE_LABELS[type] || type}
          </span>

          {/* プロジェクト・ターゲット */}
          <div className="flex-1 min-w-0">
            <span className="text-sm text-gray-700 truncate">
              {projectId} / {targetId}
            </span>
          </div>

          {/* 時刻・所要時間 */}
          <div className="flex-shrink-0 text-xs text-gray-500">
            {formatTime(startedAt)}
            {result?.durationMs && (
              <span className="ml-2 text-gray-400">
                ({formatDuration(result.durationMs)})
              </span>
            )}
          </div>
        </div>

        {/* 展開アイコン */}
        {!isRunning && (
          <svg
            className={`w-4 h-4 text-gray-400 ml-2 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {/* 展開時の詳細 */}
      {isExpanded && result && (
        <ExecutionLogDetail result={result} />
      )}
    </div>
  );
};

// =============================================================================
// 詳細表示コンポーネント（TASK_575相当 - 統合実装）
// =============================================================================

interface ExecutionLogDetailProps {
  result: ExecutionResult;
}

const ExecutionLogDetail: React.FC<ExecutionLogDetailProps> = ({ result }) => {
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const handleCopy = useCallback(async (text: string, field: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 1500);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  }, []);

  return (
    <div className="border-t border-gray-200 bg-white p-4 space-y-4">
      {/* エラーメッセージ */}
      {result.error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-3">
          <div className="flex items-start gap-2">
            <svg className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span className="text-sm text-red-700">{result.error}</span>
          </div>
        </div>
      )}

      {/* 実行情報 */}
      <div className="grid grid-cols-2 gap-4 text-xs">
        <div>
          <span className="text-gray-500">実行ID:</span>
          <span className="ml-2 font-mono text-gray-700">{result.executionId}</span>
        </div>
        <div>
          <span className="text-gray-500">終了コード:</span>
          <span className={`ml-2 font-mono ${result.exitCode === 0 ? 'text-green-600' : 'text-red-600'}`}>
            {result.exitCode ?? 'N/A'}
          </span>
        </div>
        <div>
          <span className="text-gray-500">開始:</span>
          <span className="ml-2 text-gray-700">{formatDateTime(result.startedAt)}</span>
        </div>
        <div>
          <span className="text-gray-500">終了:</span>
          <span className="ml-2 text-gray-700">{formatDateTime(result.completedAt)}</span>
        </div>
      </div>

      {/* stdout */}
      {result.stdout && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-gray-600">stdout</span>
            <button
              onClick={() => handleCopy(result.stdout, 'stdout')}
              className="text-xs text-gray-400 hover:text-blue-600 transition-colors"
            >
              {copiedField === 'stdout' ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <pre className="bg-gray-900 text-gray-100 text-xs p-3 rounded-lg overflow-auto max-h-64 font-mono whitespace-pre-wrap">
            {result.stdout}
          </pre>
        </div>
      )}

      {/* stderr */}
      {result.stderr && result.stderr.trim() && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-red-600">stderr</span>
            <button
              onClick={() => handleCopy(result.stderr, 'stderr')}
              className="text-xs text-gray-400 hover:text-blue-600 transition-colors"
            >
              {copiedField === 'stderr' ? 'Copied!' : 'Copy'}
            </button>
          </div>
          <pre className="bg-red-900 text-red-100 text-xs p-3 rounded-lg overflow-auto max-h-64 font-mono whitespace-pre-wrap">
            {result.stderr}
          </pre>
        </div>
      )}
    </div>
  );
};

// =============================================================================
// ユーティリティ関数
// =============================================================================

/**
 * 日時フォーマット（HH:mm:ss）
 */
function formatTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('ja-JP', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

/**
 * 日時フォーマット（YYYY/MM/DD HH:mm:ss）
 */
function formatDateTime(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    return date.toLocaleString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return dateStr;
  }
}

/**
 * 所要時間フォーマット
 */
function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${ms}ms`;
  }
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

/**
 * ファイルサイズフォーマット
 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// =============================================================================
// エクスポート
// =============================================================================

export default ExecutionLog;
