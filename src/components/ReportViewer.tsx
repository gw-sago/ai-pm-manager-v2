/**
 * ReportViewer.tsx - REPORT閲覧コンポーネント
 *
 * TASKクリック時にREPORTファイルを表示するコンポーネント。
 * MarkdownViewerを使用したMarkdownレンダリング対応。REPORTがない場合は適切なメッセージを表示。
 *
 * TASK_193: ReportViewer 実装
 * TASK_1123: MarkdownViewerへのリファクタリング（重複コード解消）
 */

import React, { useState, useEffect } from 'react';
import type { TaskInfo } from '../preload';
import { MarkdownViewer } from './MarkdownViewer';

/**
 * ReportViewerProps
 */
interface ReportViewerProps {
  /** プロジェクト名 */
  projectName: string;
  /** 選択されたタスク情報 */
  task: TaskInfo;
  /** 閉じるボタンのコールバック */
  onClose: () => void;
}

/**
 * ステータスバッジコンポーネント
 */
const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const getStatusStyle = () => {
    switch (status.toUpperCase()) {
      case 'COMPLETED':
        return 'bg-green-100 text-green-800';
      case 'IN_PROGRESS':
        return 'bg-blue-100 text-blue-800';
      case 'DONE':
        return 'bg-teal-100 text-teal-800';
      case 'REWORK':
        return 'bg-red-100 text-red-800';
      case 'BLOCKED':
        return 'bg-orange-100 text-orange-800';
      case 'QUEUED':
        return 'bg-gray-100 text-gray-800';
      default:
        return 'bg-gray-100 text-gray-600';
    }
  };

  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${getStatusStyle()}`}>
      {status}
    </span>
  );
};

/**
 * ReportViewerコンポーネント
 *
 * TASKクリック時にREPORTを表示するパネル。
 * - TASK ID、タイトル、ステータス表示
 * - REPORTファイル内容のMarkdownレンダリング（MarkdownViewer使用）
 * - REPORTがない場合のメッセージ表示
 * - ファイルパス表示
 */
export const ReportViewer: React.FC<ReportViewerProps> = ({
  projectName,
  task,
  onClose,
}) => {
  const [reportContent, setReportContent] = useState<string | null>(null);
  const [reportPath, setReportPath] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // REPORTファイルの読み込み
  useEffect(() => {
    const loadReport = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const content = await window.electronAPI.getReportFile(projectName, task.id);
        setReportContent(content);

        // REPORTファイルパスを推測（ProjectServiceの実装に基づく）
        // PROJECTS/{project}/RESULT/ORDER_{id}/09_REPORTS/REPORT_{task_id}.md
        // または 05_REPORT/REPORT_{task_id}.md
        if (content) {
          // ORDER IDをタスクから推測（task.orderIdがあれば使用、なければ「-」）
          const orderId = (task as { orderId?: string }).orderId || '-';
          setReportPath(`PROJECTS/${projectName}/RESULT/${orderId}/05_REPORT/REPORT_${task.id.replace('TASK_', '')}.md`);
        }
      } catch (err) {
        console.error('[ReportViewer] Failed to load report:', err);
        setError('REPORTファイルの読み込みに失敗しました');
      } finally {
        setIsLoading(false);
      }
    };

    loadReport();
  }, [projectName, task.id, task]);

  // ESCキーで閉じる
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // REPORTがあるかどうか
  const hasReport = reportContent !== null && reportContent.trim() !== '';

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="report-viewer-title"
    >
      <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col m-4">
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            <span className="text-sm font-mono text-gray-500">{task.id}</span>
            <StatusBadge status={task.status} />
            <h2 id="report-viewer-title" className="text-lg font-semibold text-gray-900 truncate max-w-[400px]">
              {task.title}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-full hover:bg-gray-100 transition-colors"
            aria-label="閉じる"
          >
            <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* コンテンツ */}
        <div className="flex-1 overflow-auto p-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-48">
              <div className="flex items-center space-x-2">
                <svg className="w-5 h-5 text-blue-500 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                <span className="text-gray-500">読み込み中...</span>
              </div>
            </div>
          ) : error ? (
            <div className="flex items-center justify-center h-48">
              <div className="text-center">
                <svg className="w-12 h-12 text-red-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <p className="text-gray-500">{error}</p>
              </div>
            </div>
          ) : hasReport ? (
            <MarkdownViewer content={reportContent as string} />
          ) : (
            <div className="flex items-center justify-center h-48">
              <div className="text-center">
                <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
                <h3 className="text-lg font-medium text-gray-700 mb-2">REPORTなし</h3>
                <p className="text-sm text-gray-500 max-w-xs mx-auto">
                  このタスクにはまだREPORTファイルが作成されていません。
                  タスク完了後にREPORTが生成されます。
                </p>
              </div>
            </div>
          )}
        </div>

        {/* フッター：ファイルパス表示 + 閉じるボタン */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-gray-200 bg-gray-50">
          {/* ファイルパス表示 */}
          <div className="flex items-center text-xs text-gray-500">
            {hasReport && reportPath && (
              <>
                <svg className="w-4 h-4 mr-1 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
                  />
                </svg>
                <span className="truncate max-w-md" title={reportPath}>
                  {reportPath}
                </span>
              </>
            )}
          </div>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-100 text-gray-700 rounded hover:bg-gray-200 transition-colors"
          >
            閉じる
          </button>
        </div>
      </div>
    </div>
  );
};
