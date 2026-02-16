/**
 * TaskLogModal - タスク実行ログモーダル
 *
 * ORDER_128 / TASK_1129: エラーハンドリングと詳細ログ遷移機能
 * FloatingProgressPanelからタスククリック時に表示する詳細ログモーダル
 *
 * @module TaskLogModal
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import type { WorkerLogContent } from '../preload';

interface TaskLogModalProps {
  /** タスクID */
  taskId: string;
  /** プロジェクトID */
  projectId: string;
  /** ログファイルパス（オプション） */
  logFile?: string;
  /** エラー状態フラグ */
  hasError?: boolean;
  /** 閉じるコールバック */
  onClose: () => void;
}

/**
 * TaskLogModal Component
 */
export const TaskLogModal: React.FC<TaskLogModalProps> = ({
  taskId,
  projectId,
  logFile,
  hasError = false,
  onClose,
}) => {
  const [logContent, setLogContent] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);
  const lastLogSizeRef = useRef<number>(0);

  /**
   * ログファイルを読み込む
   */
  const loadLog = useCallback(async () => {
    if (!logFile && !taskId) {
      setError('ログファイルまたはタスクIDが指定されていません');
      setIsLoading(false);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      // ログファイルパスが指定されている場合はそのまま使用
      // そうでない場合はタスクIDから最新ログを取得
      let logData: WorkerLogContent | null = null;

      if (logFile) {
        logData = await window.electronAPI.readWorkerLog(logFile);
      } else {
        // タスクIDから最新ログを検索
        const logs = await window.electronAPI.getWorkerLogs(projectId);
        const taskLog = logs.find(l => l.taskId === taskId);
        if (taskLog) {
          logData = await window.electronAPI.readWorkerLog(taskLog.filePath);
        }
      }

      if (logData) {
        setLogContent(logData.content);
        lastLogSizeRef.current = logData.fileSize;
      } else {
        setError('ログファイルが見つかりません');
      }
    } catch (err) {
      console.error('[TaskLogModal] Failed to load log:', err);
      setError(err instanceof Error ? err.message : 'ログの読み込みに失敗しました');
    } finally {
      setIsLoading(false);
    }
  }, [logFile, taskId, projectId]);

  /**
   * 初回ログ読み込み
   */
  useEffect(() => {
    loadLog();
  }, [loadLog]);

  /**
   * ログ更新監視（5秒ごとにポーリング）
   */
  useEffect(() => {
    if (!logFile) return;

    const intervalId = setInterval(async () => {
      try {
        const logData = await window.electronAPI.readWorkerLog(logFile);
        if (logData && logData.fileSize > lastLogSizeRef.current) {
          setLogContent(logData.content);
          lastLogSizeRef.current = logData.fileSize;
        }
      } catch (err) {
        console.error('[TaskLogModal] Failed to refresh log:', err);
      }
    }, 5000);

    return () => clearInterval(intervalId);
  }, [logFile]);

  /**
   * 自動スクロール
   */
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [logContent, autoScroll]);

  /**
   * スクロール位置を監視して自動スクロールを制御
   */
  const handleScroll = useCallback(() => {
    if (!logContainerRef.current) return;

    const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    setAutoScroll(isAtBottom);
  }, []);

  /**
   * ログ行の色付け（エラー・警告のハイライト）
   */
  const renderLogLine = (line: string, index: number) => {
    const isError = line.includes('ERROR') || line.includes('[ERROR]') || line.includes('Exception');
    const isWarning = line.includes('WARN') || line.includes('[WARN]') || line.includes('WARNING');

    const lineClass = isError
      ? 'text-red-400 bg-red-900/20'
      : isWarning
      ? 'text-yellow-400 bg-yellow-900/20'
      : 'text-gray-300';

    return (
      <div key={index} className={`font-mono text-xs whitespace-pre-wrap ${lineClass} px-2 py-0.5`}>
        {line}
      </div>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-gray-900 rounded-lg shadow-xl w-[90vw] h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ヘッダー */}
        <div className={`flex items-center justify-between px-4 py-3 border-b ${
          hasError ? 'bg-red-900 border-red-700' : 'bg-gray-800 border-gray-700'
        }`}>
          <div className="flex items-center gap-3">
            {hasError && (
              <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            )}
            <h2 className="text-lg font-semibold text-white">
              {taskId} - 実行ログ
            </h2>
            {hasError && (
              <span className="px-2 py-1 text-xs font-medium text-red-300 bg-red-800 rounded">
                エラー発生
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={loadLog}
              disabled={isLoading}
              className="px-3 py-1 text-sm text-gray-300 hover:text-white hover:bg-gray-700 rounded transition-colors disabled:opacity-50"
              title="ログを再読み込み"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
            <button
              onClick={onClose}
              className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
              title="閉じる"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        {/* ログ内容 */}
        <div
          ref={logContainerRef}
          onScroll={handleScroll}
          className="flex-1 overflow-y-auto bg-gray-950 p-2"
        >
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex items-center gap-2 text-gray-400">
                <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>読み込み中...</span>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-full">
              <div className="text-red-400 bg-red-900/20 px-4 py-2 rounded">
                {error}
              </div>
            </div>
          ) : logContent ? (
            <div>
              {logContent.split('\n').map((line, index) => renderLogLine(line, index))}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              ログがありません
            </div>
          )}
        </div>

        {/* フッター */}
        <div className="flex items-center justify-between px-4 py-2 bg-gray-800 border-t border-gray-700">
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="rounded"
              />
              自動スクロール
            </label>
          </div>
          <div className="text-xs text-gray-500">
            {logContent.split('\n').length.toLocaleString()} 行
          </div>
        </div>
      </div>
    </div>
  );
};
