/**
 * TaskDetailPanel Component
 *
 * ORDER_126 / TASK_1119: タスク詳細パネルコンポーネント
 * ORDER_003 / TASK_005: タスク定義・レポート表示・復旧プロンプト機能追加
 * ORDER_008 / TASK_021: タブ構造リファクタリング（PM指示/実行結果/レビュー）
 *
 * タスク詳細情報を表示するモーダル/サイドパネルコンポーネント。
 * 3タブ構造:
 * - PM指示タブ: タスク定義ファイル（TASK_XXX.md）、説明
 * - 実行結果タブ: 実行レポート（REPORT_XXX.md）、基本情報、タイムスタンプ
 * - レビュータブ: 差し戻し情報、レビュー履歴、エスカレーション、ステータス遷移
 * 共通エリア: ヘッダー、タイトル、復旧プロンプト、依存タスク、フッター
 */

import React, { useEffect, useState, useCallback } from 'react';
import type { AipmTask, TaskReviewHistory } from '../preload';
import { MarkdownViewer } from './MarkdownViewer';

interface TaskDetailPanelProps {
  /** プロジェクトID */
  projectId: string;
  /** タスクID */
  taskId: string;
  /** 閉じる時のコールバック */
  onClose: () => void;
  /** タスククリック時のコールバック（依存タスク遷移用） */
  onTaskClick?: (taskId: string) => void;
  /** 表示形式（モーダル or サイドパネル） */
  mode?: 'modal' | 'sidepanel';
}

/**
 * ステータスバッジコンポーネント
 */
const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const colorMap: Record<string, { bg: string; text: string }> = {
    QUEUED: { bg: 'bg-gray-200', text: 'text-gray-700' },
    BLOCKED: { bg: 'bg-red-100', text: 'text-red-700' },
    IN_PROGRESS: { bg: 'bg-blue-200', text: 'text-blue-700' },
    IN_REVIEW: { bg: 'bg-orange-200', text: 'text-orange-700' },
    DONE: { bg: 'bg-green-100', text: 'text-green-700' },
    REWORK: { bg: 'bg-red-200', text: 'text-red-800' },
    COMPLETED: { bg: 'bg-green-200', text: 'text-green-800' },
    CANCELLED: { bg: 'bg-gray-300', text: 'text-gray-500' },
    REJECTED: { bg: 'bg-red-300', text: 'text-red-900' },
    SKIPPED: { bg: 'bg-gray-100', text: 'text-gray-400' },
  };

  const colors = colorMap[status] || colorMap.QUEUED;

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${colors.bg} ${colors.text}`}>
      {status}
    </span>
  );
};

/**
 * 優先度バッジコンポーネント
 */
const PriorityBadge: React.FC<{ priority: string }> = ({ priority }) => {
  const colorMap: Record<string, { bg: string; text: string }> = {
    P0: { bg: 'bg-red-100', text: 'text-red-700' },
    P1: { bg: 'bg-orange-100', text: 'text-orange-700' },
    P2: { bg: 'bg-yellow-100', text: 'text-yellow-700' },
    P3: { bg: 'bg-green-100', text: 'text-green-700' },
  };

  const colors = colorMap[priority] || colorMap.P1;

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${colors.bg} ${colors.text}`}>
      {priority}
    </span>
  );
};

/**
 * 折りたたみ可能セクションコンポーネント
 */
const CollapsibleSection: React.FC<{
  title: string;
  count?: number;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}> = ({ title, count, defaultExpanded = true, children }) => {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 hover:text-gray-700 transition"
        >
          <svg
            className={`w-4 h-4 transform transition-transform ${expanded ? 'rotate-90' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span>{title}{count !== undefined ? ` (${count})` : ''}</span>
        </button>
      </h3>
      {expanded && children}
    </div>
  );
};

/**
 * 日時フォーマット関数
 */
const formatDateTime = (dateStr: string | null): string => {
  if (!dateStr) return 'N/A';
  try {
    const date = new Date(dateStr);
    return date.toLocaleString('ja-JP', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return dateStr;
  }
};

/** 異常状態の判定 */
const isAbnormalStatus = (status: string): boolean => {
  return ['INTERRUPTED', 'ESCALATED', 'REWORK', 'REJECTED'].includes(status);
};

/** タブ種別 */
type TabId = 'pm' | 'result' | 'review';

const TAB_DEFINITIONS: { id: TabId; label: string; icon: string }[] = [
  { id: 'pm', label: 'PM指示', icon: '\u{1F4CB}' },
  { id: 'result', label: '実行結果', icon: '\u{1F4CA}' },
  { id: 'review', label: 'レビュー', icon: '\u{1F50D}' },
];

/**
 * TaskDetailPanel コンポーネント
 */
export const TaskDetailPanel: React.FC<TaskDetailPanelProps> = ({
  projectId,
  taskId,
  onClose,
  onTaskClick,
  mode = 'modal',
}) => {
  const [task, setTask] = useState<AipmTask | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reviewHistory, setReviewHistory] = useState<TaskReviewHistory | null>(null);
  const [timelineExpanded, setTimelineExpanded] = useState(false);
  const [taskFileContent, setTaskFileContent] = useState<string | null>(null);
  const [reportFileContent, setReportFileContent] = useState<string | null>(null);
  const [promptCopied, setPromptCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>('pm');
  const [orderStructureHistory, setOrderStructureHistory] = useState<Array<{
    fieldName: string;
    oldValue: string | null;
    newValue: string | null;
    changedBy: string | null;
    changeReason: string | null;
    changedAt: string;
  }>>([]);

  // タスク詳細を取得
  const fetchTaskDetail = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const taskDetail = await window.electronAPI.getTask(taskId, projectId);

      if (taskDetail) {
        setTask(taskDetail);
      } else {
        setError(`タスク ${taskId} が見つかりませんでした。`);
      }
    } catch (err) {
      console.error('[TaskDetailPanel] Failed to fetch task detail:', err);
      setError('タスク詳細の取得に失敗しました。');
    } finally {
      setLoading(false);
    }
  }, [taskId, projectId]);

  useEffect(() => {
    fetchTaskDetail();
  }, [fetchTaskDetail]);

  // DB変更イベントの購読（ORDER_004 / TASK_011）
  // スクリプト実行完了・タスクステータス変更時にタスク詳細を自動更新
  useEffect(() => {
    const unsubscribe = window.electronAPI.onDbChanged((event) => {
      // 現在表示中のプロジェクトに関係するイベントのみ再フェッチ
      if (event.projectId === projectId) {
        console.log('[TaskDetailPanel] db:changed event received:', event.source, event.targetId);
        // ローディング表示は抑制して静かに更新（タスク詳細は既に表示されているため）
        window.electronAPI.getTask(taskId, projectId)
          .then((taskDetail) => {
            if (taskDetail) {
              setTask(taskDetail);
            }
          })
          .catch((err) => {
            console.error('[TaskDetailPanel] Failed to refresh task via db:changed:', err);
          });
      }
    });

    return () => {
      unsubscribe();
    };
  }, [taskId, projectId]);

  // レビュー履歴を取得
  useEffect(() => {
    let cancelled = false;

    const fetchReviewHistory = async () => {
      try {
        const history = await window.electronAPI.getTaskReviewHistory(projectId, taskId);
        if (!cancelled) {
          setReviewHistory(history);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[TaskDetailPanel] Failed to fetch review history:', err);
        }
      }
    };

    fetchReviewHistory();

    return () => {
      cancelled = true;
    };
  }, [taskId, projectId]);

  // ORDER全体のタスク構成変更履歴を取得（ORDER_009 / TASK_025）
  useEffect(() => {
    let cancelled = false;

    const fetchOrderStructureHistory = async () => {
      if (!task?.orderId) return;
      try {
        const history = await window.electronAPI.getOrderStructureHistory(projectId, task.orderId);
        if (!cancelled) {
          setOrderStructureHistory(history);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[TaskDetailPanel] Failed to fetch order structure history:', err);
        }
      }
    };

    fetchOrderStructureHistory();

    return () => {
      cancelled = true;
    };
  }, [task?.orderId, projectId]);

  // タスク定義ファイル・レポートファイルを取得
  useEffect(() => {
    let cancelled = false;

    const fetchFiles = async () => {
      try {
        const [taskFile, reportFile] = await Promise.all([
          window.electronAPI.getTaskFile(projectId, taskId),
          window.electronAPI.getReportFile(projectId, taskId),
        ]);
        if (!cancelled) {
          setTaskFileContent(taskFile);
          setReportFileContent(reportFile);
        }
      } catch (err) {
        if (!cancelled) {
          console.error('[TaskDetailPanel] Failed to fetch task/report files:', err);
        }
      }
    };

    fetchFiles();

    return () => {
      cancelled = true;
    };
  }, [taskId, projectId]);

  // Escキーで閉じる
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [onClose]);

  // モーダルの背景クリックで閉じる（モーダルモードのみ）
  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (mode === 'modal' && e.target === e.currentTarget) {
      onClose();
    }
  };

  // 依存タスククリックハンドラ
  const handleDependencyClick = (depTaskId: string) => {
    if (onTaskClick) {
      onTaskClick(depTaskId);
    }
  };

  // 復旧プロンプト生成・コピー
  const handleCopyRecoveryPrompt = useCallback(async () => {
    if (!task) return;

    // 最新の差し戻し理由またはエスカレーション理由を取得
    let reason = '';
    if (reviewHistory) {
      if (task.status === 'REWORK' || task.status === 'REJECTED') {
        const latestRejection = reviewHistory.reviews
          .filter((r) => r.status === 'REJECTED' && r.comment)
          .sort((a, b) => {
            const dateA = a.reviewedAt || a.submittedAt || '';
            const dateB = b.reviewedAt || b.submittedAt || '';
            return dateB.localeCompare(dateA);
          })[0];
        if (latestRejection) {
          reason = latestRejection.comment || '';
        }
      } else if (task.status === 'ESCALATED') {
        const latestEscalation = reviewHistory.escalations
          .filter((e) => !e.resolvedAt)
          .sort((a, b) => b.createdAt.localeCompare(a.createdAt))[0];
        if (latestEscalation) {
          reason = latestEscalation.reason || '';
        }
      }
    }

    const prompt = [
      `## 復旧対象タスク`,
      ``,
      `- プロジェクト: ${projectId}`,
      `- タスク: ${task.id} - ${task.title}`,
      `- ORDER: ${task.orderId}`,
      `- 現在の状態: ${task.status}`,
      reason ? `- 理由: ${reason}` : null,
      ``,
      `## 復旧コマンド`,
      ``,
      '```',
      `/aipm-recover ${projectId} ${task.id}`,
      '```',
      ``,
      `## 手動復旧の場合`,
      ``,
      '```',
      `/aipm-worker ${projectId} ${task.id}`,
      '```',
    ].filter((line) => line !== null).join('\n');

    try {
      await navigator.clipboard.writeText(prompt);
      setPromptCopied(true);
      setTimeout(() => setPromptCopied(false), 2000);
    } catch (err) {
      console.error('[TaskDetailPanel] Failed to copy to clipboard:', err);
    }
  }, [task, reviewHistory, projectId]);

  // ローディング表示
  if (loading) {
    return (
      <div
        className={`${
          mode === 'modal'
            ? 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50'
            : 'w-full h-full flex items-center justify-center'
        }`}
        onClick={handleBackdropClick}
      >
        <div className="bg-white rounded-lg shadow-xl p-8">
          <div className="flex items-center space-x-3">
            <svg className="animate-spin h-6 w-6 text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            <span className="text-gray-700">読み込み中...</span>
          </div>
        </div>
      </div>
    );
  }

  // エラー表示
  if (error || !task) {
    return (
      <div
        className={`${
          mode === 'modal'
            ? 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50'
            : 'w-full h-full flex items-center justify-center'
        }`}
        onClick={handleBackdropClick}
      >
        <div className="bg-white rounded-lg shadow-xl p-8 max-w-md">
          <div className="text-center">
            <svg className="w-12 h-12 text-red-500 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">エラー</h3>
            <p className="text-gray-600 mb-4">{error || 'タスクが見つかりませんでした。'}</p>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition"
            >
              閉じる
            </button>
          </div>
        </div>
      </div>
    );
  }

  // メインコンテンツ
  const content = (
    <div className="flex flex-col h-full">
      {/* ヘッダー */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 flex-shrink-0">
        <div className="flex items-center space-x-3">
          <h2 className="text-2xl font-bold text-gray-900">{task.id}</h2>
          <StatusBadge status={task.status} />
          <PriorityBadge priority={task.priority} />
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 transition"
          aria-label="閉じる"
        >
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* タイトル（共通エリア） */}
      <div className="px-6 py-3 border-b border-gray-100 flex-shrink-0">
        <p className="text-lg text-gray-900 font-medium">{task.title}</p>
      </div>

      {/* 復旧プロンプト（異常状態時、共通エリア） */}
      {isAbnormalStatus(task.status) && (
        <div className="mx-6 mt-3 bg-amber-50 rounded-lg p-3 border border-amber-200 flex-shrink-0">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-sm font-semibold text-amber-800 uppercase">復旧サポート</h3>
            <button
              onClick={handleCopyRecoveryPrompt}
              className={`px-3 py-1 rounded text-sm font-medium transition ${
                promptCopied
                  ? 'bg-green-500 text-white'
                  : 'bg-amber-600 text-white hover:bg-amber-700'
              }`}
            >
              {promptCopied ? 'コピー完了!' : '復旧プロンプトをコピー'}
            </button>
          </div>
          <p className="text-sm text-amber-700">
            CLIから復旧するためのプロンプトをクリップボードにコピーします。
          </p>
        </div>
      )}

      {/* タブバー */}
      <div className="flex border-b border-gray-200 px-6 flex-shrink-0">
        {TAB_DEFINITIONS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <span className="mr-1.5">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* タブコンテンツ */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6 min-h-0">
        {/* === PM指示タブ === */}
        {activeTab === 'pm' && (
          <>
            {/* タスク定義ファイル */}
            <CollapsibleSection title="タスク定義" defaultExpanded={true}>
              {taskFileContent ? (
                <div
                  className="bg-blue-50 rounded-lg border border-blue-100 overflow-x-auto task-definition-section"
                  style={{ maxHeight: '400px', overflowY: 'auto' }}
                >
                  <MarkdownViewer content={taskFileContent} />
                </div>
              ) : (
                <p className="text-sm text-gray-400 italic">タスク定義ファイルなし</p>
              )}
            </CollapsibleSection>

            {/* 説明（Markdown） */}
            {task.description && (
              <CollapsibleSection title="説明" defaultExpanded={true}>
                <div
                  className="bg-gray-50 rounded-lg overflow-x-auto task-definition-section"
                >
                  <MarkdownViewer content={task.description} />
                </div>
              </CollapsibleSection>
            )}

            {/* 依存タスク */}
            {task.dependencies.length > 0 && task.dependencies[0] !== '-' && (
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">
                  依存タスク ({task.dependencies.length})
                </h3>
                <div className="flex flex-wrap gap-2">
                  {task.dependencies.map((depTaskId) => (
                    <button
                      key={depTaskId}
                      onClick={() => handleDependencyClick(depTaskId)}
                      className="px-3 py-1 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 transition text-sm font-medium"
                    >
                      {depTaskId}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* === 実行結果タブ === */}
        {activeTab === 'result' && (
          <>
            {/* 実行レポート */}
            <CollapsibleSection title="実行レポート" defaultExpanded={true}>
              {reportFileContent ? (
                <div
                  className="bg-green-50 rounded-lg border border-green-100 overflow-x-auto task-definition-section"
                  style={{ maxHeight: '400px', overflowY: 'auto' }}
                >
                  <MarkdownViewer content={reportFileContent} />
                </div>
              ) : (
                <p className="text-sm text-gray-400 italic">実行レポートなし</p>
              )}
            </CollapsibleSection>

            {/* 基本情報 */}
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-3">基本情報</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="text-xs font-medium text-gray-400 mb-1">ORDER ID</h4>
                  <p className="text-gray-900">{task.orderId}</p>
                </div>
                <div>
                  <h4 className="text-xs font-medium text-gray-400 mb-1">推奨モデル</h4>
                  <p className="text-gray-900">{task.recommendedModel}</p>
                </div>
                <div>
                  <h4 className="text-xs font-medium text-gray-400 mb-1">担当Worker</h4>
                  <p className="text-gray-900">{task.assignee || 'N/A'}</p>
                </div>
                <div>
                  <h4 className="text-xs font-medium text-gray-400 mb-1">プロジェクトID</h4>
                  <p className="text-gray-900">{task.projectId}</p>
                </div>
              </div>
            </div>

            {/* タイムスタンプ */}
            <div>
              <h3 className="text-sm font-semibold text-gray-500 uppercase mb-3">タイムスタンプ</h3>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="text-xs font-medium text-gray-400 mb-1">開始日時</h4>
                  <p className="text-gray-900">{formatDateTime(task.startedAt)}</p>
                </div>
                <div>
                  <h4 className="text-xs font-medium text-gray-400 mb-1">完了日時</h4>
                  <p className="text-gray-900">{formatDateTime(task.completedAt)}</p>
                </div>
                <div>
                  <h4 className="text-xs font-medium text-gray-400 mb-1">作成日時</h4>
                  <p className="text-gray-900">{formatDateTime(task.createdAt)}</p>
                </div>
                <div>
                  <h4 className="text-xs font-medium text-gray-400 mb-1">更新日時</h4>
                  <p className="text-gray-900">{formatDateTime(task.updatedAt)}</p>
                </div>
              </div>
            </div>
          </>
        )}

        {/* === レビュータブ === */}
        {activeTab === 'review' && (
          <>
            {/* 差し戻し情報 */}
            {reviewHistory && (reviewHistory.rejectCount > 0 || task.status === 'REWORK' || task.status === 'REJECTED') && (
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">差し戻し情報</h3>
                <div className="bg-red-50 rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium text-red-800">
                      差し戻し: {reviewHistory.rejectCount}/{reviewHistory.maxRework}回
                    </span>
                    {reviewHistory.rejectCount >= reviewHistory.maxRework && (
                      <span className="text-xs font-medium text-red-600 bg-red-100 px-2 py-0.5 rounded">上限到達</span>
                    )}
                  </div>
                  <div className="w-full bg-red-200 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full ${
                        reviewHistory.rejectCount >= reviewHistory.maxRework ? 'bg-red-600' : 'bg-red-400'
                      }`}
                      style={{
                        width: `${Math.min((reviewHistory.rejectCount / Math.max(reviewHistory.maxRework, 1)) * 100, 100)}%`,
                      }}
                    />
                  </div>
                  {task.status === 'REWORK' && (() => {
                    const latestRejection = reviewHistory.reviews
                      .filter((r) => r.status === 'REJECTED' && r.comment)
                      .sort((a, b) => {
                        const dateA = a.reviewedAt || a.submittedAt || '';
                        const dateB = b.reviewedAt || b.submittedAt || '';
                        return dateB.localeCompare(dateA);
                      })[0];
                    return latestRejection ? (
                      <div className="mt-3 p-3 bg-red-100 rounded border border-red-200">
                        <p className="text-xs font-semibold text-red-700 mb-1">最新の差し戻し理由:</p>
                        <p className="text-sm text-red-800">{latestRejection.comment}</p>
                      </div>
                    ) : null;
                  })()}
                </div>
              </div>
            )}

            {/* レビュー履歴 */}
            <CollapsibleSection
              title="レビュー履歴"
              count={reviewHistory?.reviews.length}
              defaultExpanded={true}
            >
              {reviewHistory && reviewHistory.reviews.length > 0 ? (
                <div className="space-y-2">
                  {[...reviewHistory.reviews]
                    .sort((a, b) => {
                      const dateA = a.reviewedAt || a.submittedAt || '';
                      const dateB = b.reviewedAt || b.submittedAt || '';
                      return dateB.localeCompare(dateA);
                    })
                    .map((review) => {
                      const statusConfig: Record<string, { icon: string; color: string; bgColor: string }> = {
                        APPROVED: { icon: '\u2713', color: 'text-green-700', bgColor: 'bg-green-100' },
                        REJECTED: { icon: '\u2717', color: 'text-red-700', bgColor: 'bg-red-100' },
                        ESCALATED: { icon: '\u26A0', color: 'text-yellow-700', bgColor: 'bg-yellow-100' },
                        PENDING: { icon: '\u25CB', color: 'text-gray-500', bgColor: 'bg-gray-100' },
                        IN_REVIEW: { icon: '\u25CB', color: 'text-gray-500', bgColor: 'bg-gray-100' },
                      };
                      const config = statusConfig[review.status] || statusConfig.PENDING;

                      return (
                        <div
                          key={review.id}
                          className={`flex items-start gap-3 p-3 rounded-lg ${config.bgColor}`}
                        >
                          <span className={`text-lg font-bold ${config.color} flex-shrink-0 w-6 text-center`}>
                            {config.icon}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className={`text-sm font-semibold ${config.color}`}>
                                {review.status}
                              </span>
                              {review.reviewer && (
                                <span className="text-xs text-gray-600">by {review.reviewer}</span>
                              )}
                              <span className="text-xs text-gray-500">
                                {formatDateTime(review.reviewedAt || review.submittedAt)}
                              </span>
                            </div>
                            {review.comment && (
                              <p className="text-sm text-gray-700 mt-1">{review.comment}</p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                </div>
              ) : (
                <p className="text-sm text-gray-400">レビュー履歴なし</p>
              )}
            </CollapsibleSection>

            {/* エスカレーション情報 */}
            {reviewHistory && (task.status === 'ESCALATED' || reviewHistory.escalations.length > 0) && (
              <CollapsibleSection
                title="エスカレーション情報"
                count={reviewHistory.escalations.length}
                defaultExpanded={true}
              >
                <div className="space-y-2">
                  {reviewHistory.escalations.map((esc) => (
                    <div
                      key={esc.id}
                      className={`p-3 rounded-lg border ${
                        esc.resolvedAt
                          ? 'bg-green-50 border-green-200'
                          : 'bg-yellow-50 border-yellow-200'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-sm font-semibold ${
                          esc.resolvedAt ? 'text-green-700' : 'text-yellow-700'
                        }`}>
                          {esc.resolvedAt ? '解決済み' : '未解決'}
                        </span>
                        <span className="text-xs text-gray-500">
                          {formatDateTime(esc.createdAt)}
                        </span>
                      </div>
                      {esc.reason && (
                        <p className="text-sm text-gray-700">{esc.reason}</p>
                      )}
                      {esc.resolvedAt && esc.resolution && (
                        <div className="mt-2 pt-2 border-t border-green-200">
                          <p className="text-xs font-semibold text-green-700 mb-1">解決内容:</p>
                          <p className="text-sm text-green-800">{esc.resolution}</p>
                          <p className="text-xs text-gray-500 mt-1">{formatDateTime(esc.resolvedAt)}</p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </CollapsibleSection>
            )}

            {/* ステータス遷移 */}
            {reviewHistory && reviewHistory.statusHistory.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold text-gray-500 uppercase mb-2">
                  <button
                    onClick={() => setTimelineExpanded(!timelineExpanded)}
                    className="flex items-center gap-1 hover:text-gray-700 transition"
                  >
                    <span>ステータス遷移 ({reviewHistory.statusHistory.length})</span>
                    <svg
                      className={`w-4 h-4 transform transition-transform ${timelineExpanded ? 'rotate-180' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </h3>
                <div className="space-y-1">
                  {(() => {
                    const sorted = [...reviewHistory.statusHistory].sort((a, b) =>
                      b.changedAt.localeCompare(a.changedAt)
                    );
                    const shouldCollapse = sorted.length > 3 && !timelineExpanded;
                    const displayed = shouldCollapse ? sorted.slice(0, 3) : sorted;

                    return (
                      <>
                        {displayed.map((entry, idx) => (
                          <div
                            key={idx}
                            className="flex items-center gap-2 py-1.5 px-3 bg-gray-50 rounded text-sm"
                          >
                            <span className="text-gray-400 flex-shrink-0">
                              {formatDateTime(entry.changedAt)}
                            </span>
                            <span className="font-medium text-gray-600">{entry.oldValue || '(none)'}</span>
                            <span className="text-gray-400">{'\u2192'}</span>
                            <span className="font-medium text-gray-900">{entry.newValue || '(none)'}</span>
                            {entry.changeReason && (
                              <span className="text-xs text-gray-500 ml-auto truncate max-w-[200px]" title={entry.changeReason}>
                                {entry.changeReason}
                              </span>
                            )}
                          </div>
                        ))}
                        {shouldCollapse && (
                          <button
                            onClick={() => setTimelineExpanded(true)}
                            className="text-xs text-blue-500 hover:text-blue-700 transition pl-3 py-1"
                          >
                            ... 他 {sorted.length - 3} 件を表示
                          </button>
                        )}
                      </>
                    );
                  })()}
                </div>
              </div>
            )}

            {/* 変更履歴（ORDER_008 / TASK_023） */}
            {reviewHistory && reviewHistory.fieldChanges && reviewHistory.fieldChanges.length > 0 && (
              <CollapsibleSection
                title="変更履歴"
                count={reviewHistory.fieldChanges.length}
                defaultExpanded={false}
              >
                <div className="space-y-1">
                  {reviewHistory.fieldChanges.map((change, idx) => {
                    const fieldNameMap: Record<string, string> = {
                      assignee: '担当Worker',
                      title: 'タイトル',
                      description: '説明',
                      priority: '優先度',
                      recommended_model: '推奨モデル',
                      markdown_created: 'MD生成',
                      dependencies: '依存関係',
                    };
                    const displayFieldName = fieldNameMap[change.fieldName] || change.fieldName;

                    return (
                      <div
                        key={idx}
                        className="py-2 px-3 bg-purple-50 rounded text-sm border border-purple-100"
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-medium text-purple-700">{displayFieldName}</span>
                          <span className="text-gray-400 text-xs">{formatDateTime(change.changedAt)}</span>
                          {change.changedBy && (
                            <span className="text-xs text-gray-500">by {change.changedBy}</span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-gray-500 text-xs truncate max-w-[200px]" title={change.oldValue || '(なし)'}>
                            {change.oldValue || '(なし)'}
                          </span>
                          <span className="text-gray-400">{'\u2192'}</span>
                          <span className="text-gray-900 text-xs truncate max-w-[200px]" title={change.newValue || '(なし)'}>
                            {change.newValue || '(なし)'}
                          </span>
                        </div>
                        {change.changeReason && (
                          <p className="text-xs text-purple-600 mt-1">{change.changeReason}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </CollapsibleSection>
            )}

            {/* タスク構成変更（ORDER_009 / TASK_025） */}
            {orderStructureHistory.length > 0 && (
              <CollapsibleSection
                title="タスク構成変更"
                count={orderStructureHistory.length}
                defaultExpanded={false}
              >
                <div className="space-y-2">
                  {orderStructureHistory.map((change, idx) => {
                    const typeConfig: Record<string, { icon: string; color: string; bgColor: string; label: string }> = {
                      task_added: { icon: '+', color: 'text-green-700', bgColor: 'bg-green-50 border-green-200', label: 'タスク追加' },
                      task_removed: { icon: '-', color: 'text-red-700', bgColor: 'bg-red-50 border-red-200', label: 'タスク削除' },
                      dependency_changed: { icon: '\u2194', color: 'text-blue-700', bgColor: 'bg-blue-50 border-blue-200', label: '依存変更' },
                      task_reordered: { icon: '\u2195', color: 'text-orange-700', bgColor: 'bg-orange-50 border-orange-200', label: '順序変更' },
                      task_restructured: { icon: '\u21BB', color: 'text-purple-700', bgColor: 'bg-purple-50 border-purple-200', label: '再構成' },
                    };
                    const config = typeConfig[change.fieldName] || typeConfig.task_restructured;

                    return (
                      <div
                        key={idx}
                        className={`p-3 rounded-lg border ${config.bgColor}`}
                      >
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`text-lg font-bold ${config.color} flex-shrink-0 w-6 text-center`}>
                            {config.icon}
                          </span>
                          <span className={`text-sm font-semibold ${config.color}`}>
                            {config.label}
                          </span>
                          <span className="text-xs text-gray-500">
                            {formatDateTime(change.changedAt)}
                          </span>
                          {change.changedBy && (
                            <span className="text-xs text-gray-500">by {change.changedBy}</span>
                          )}
                        </div>
                        {(change.oldValue || change.newValue) && (
                          <div className="flex items-center gap-2 mt-1 ml-8">
                            {change.oldValue && (
                              <span className="text-xs text-gray-500 truncate max-w-[250px]" title={change.oldValue}>
                                {change.oldValue}
                              </span>
                            )}
                            {change.oldValue && change.newValue && (
                              <span className="text-gray-400">{'\u2192'}</span>
                            )}
                            {change.newValue && (
                              <span className="text-xs text-gray-900 truncate max-w-[250px]" title={change.newValue}>
                                {change.newValue}
                              </span>
                            )}
                          </div>
                        )}
                        {change.changeReason && (
                          <p className="text-xs text-gray-600 mt-1 ml-8">{change.changeReason}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </CollapsibleSection>
            )}

            {/* レビュー情報がない場合 */}
            {(!reviewHistory || (reviewHistory.reviews.length === 0 && reviewHistory.statusHistory.length === 0 && (!reviewHistory.fieldChanges || reviewHistory.fieldChanges.length === 0))) &&
              orderStructureHistory.length === 0 &&
              !(reviewHistory && (reviewHistory.rejectCount > 0 || task.status === 'REWORK' || task.status === 'REJECTED')) && (
              <p className="text-sm text-gray-400 italic">レビュー情報はまだありません</p>
            )}
          </>
        )}
      </div>

      {/* フッター */}
      <div className="flex justify-end px-6 py-3 border-t border-gray-200 flex-shrink-0">
        <button
          onClick={onClose}
          className="px-6 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition font-medium"
        >
          閉じる
        </button>
      </div>
    </div>
  );

  // モーダルモード
  if (mode === 'modal') {
    return (
      <div
        className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
        onClick={handleBackdropClick}
      >
        <div className="bg-white rounded-lg shadow-xl max-w-5xl w-full max-h-[90vh] flex flex-col">
          {content}
        </div>
      </div>
    );
  }

  // サイドパネルモード
  return (
    <div className="fixed inset-y-0 right-0 w-1/2 bg-white shadow-xl z-50 flex flex-col">
      {content}
    </div>
  );
};
