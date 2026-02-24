/**
 * ReleaseReadinessPanel - リリース判定情報表示パネル
 *
 * ORDER_134 / TASK_1148
 *
 * タスク完了状況、レビュー結果、変更ファイル一覧、影響範囲、REPORTサマリを表示し、
 * リリース可否を色（緑・黄・赤）で視覚的に判定できるUIを提供する。
 *
 * ORDER_017 / TASK_053: リリースノート表示UIを追加
 * - 全タスクCOMPLETED時に自動生成・表示
 * - オンデマンド生成ボタンを提供
 * - MarkdownViewerでリリースノートをレンダリング
 *
 * ORDER_041 / TASK_132: レイアウト整理
 * - 折りたたみ可能なセクション構成に変更
 * - リリース情報（バージョン・日時等）をArtifactsBrowserから統合
 * - コンパクトなレイアウトに再構成
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import type { TaskInfo, OrderReleaseInfo, OrderRelatedInfo } from '../preload';
import { MarkdownViewer } from './MarkdownViewer';

interface ReleaseReadinessPanelProps {
  /** プロジェクト名 */
  projectName: string;
  /** ORDER ID */
  orderId: string;
  /** ORDER内タスク一覧 */
  tasks: TaskInfo[];
  /** リリース実行コールバック */
  onExecuteRelease?: () => void;
  /** リリース実行中フラグ */
  isReleaseRunning?: boolean;
}

/** レポートサマリ情報 */
interface ReportSummary {
  taskId: string;
  title: string;
  status: string;
  changedFiles: string[];
  summary: string;
}

/** リリース準備状況 */
type ReadinessStatus = 'ready' | 'warning' | 'blocked';

/**
 * 折りたたみセクションコンポーネント
 */
const CollapsibleSection: React.FC<{
  title: string;
  icon: React.JSX.Element;
  badge?: string | number;
  defaultExpanded?: boolean;
  children: React.ReactNode;
}> = ({ title, icon, badge, defaultExpanded = false, children }) => {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
      <button
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 active:bg-gray-100 transition-colors text-left group"
      >
        <div className="flex items-center">
          <span className="text-gray-400 group-hover:text-gray-600 transition-colors">{icon}</span>
          <span className="text-sm font-semibold text-gray-700 ml-2">{title}</span>
          {badge !== undefined && (
            <span className="ml-2 px-2 py-0.5 text-xs font-semibold bg-blue-50 text-blue-600 rounded-full">
              {badge}
            </span>
          )}
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 group-hover:text-gray-600 transition-all duration-200 ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {expanded && (
        <div className="px-4 pb-3 border-t border-gray-100">
          {children}
        </div>
      )}
    </div>
  );
};

/**
 * リリース判定情報を表示するパネルコンポーネント
 */
export const ReleaseReadinessPanel: React.FC<ReleaseReadinessPanelProps> = ({
  projectName,
  orderId,
  tasks,
  onExecuteRelease,
  isReleaseRunning = false,
}) => {
  const [reportSummaries, setReportSummaries] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ORDER_017 / TASK_053: リリースノート状態
  const [releaseNoteContent, setReleaseNoteContent] = useState<string | null>(null);
  const [releaseNoteLoading, setReleaseNoteLoading] = useState(false);
  const [releaseNoteError, setReleaseNoteError] = useState<string | null>(null);
  const [releaseNoteExpanded, setReleaseNoteExpanded] = useState(true);
  const autoFetchedRef = useRef(false);

  // TASK_132: リリース情報・関連情報（ArtifactsBrowserから移設）
  const [releaseInfo, setReleaseInfo] = useState<OrderReleaseInfo | null>(null);
  const [relatedInfo, setRelatedInfo] = useState<OrderRelatedInfo | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);

  // タスク完了状況を計算
  const completedTasks = tasks.filter(t => t.status === 'COMPLETED').length;
  const doneTasks = tasks.filter(t => t.status === 'DONE').length;
  const totalTasks = tasks.length;
  const allTasksCompleted = completedTasks === totalTasks;
  const hasIncompleteTasks = tasks.some(
    t => t.status !== 'COMPLETED' && t.status !== 'DONE'
  );

  // レビュー承認状況（DONEタスクはレビュー待ち、COMPLETEDは承認済み）
  const needsReview = doneTasks > 0;
  const allApproved = allTasksCompleted && !needsReview;

  // REWORK履歴があるかチェック（警告として表示）
  const hasReworkHistory = tasks.some((_t) => {
    // TODO: DB から rework_count を取得できる場合はそれを使用
    return false; // 現状は簡易実装
  });

  // リリース可否判定
  const getReadinessStatus = (): ReadinessStatus => {
    if (hasIncompleteTasks) return 'blocked';
    if (needsReview) return 'blocked';
    if (hasReworkHistory) return 'warning';
    if (allApproved) return 'ready';
    return 'blocked';
  };

  const readinessStatus = getReadinessStatus();

  // TASK_1150: リリースボタンを表示すべきか（全タスクCOMPLETED時 かつ コールバックが提供された時のみ）
  // ORDER_019: リリースボタンはバックログ一覧に移動したため、onExecuteReleaseが提供された場合のみ表示
  const shouldShowReleaseButton = allTasksCompleted && !!onExecuteRelease;

  // ステータスに応じた色・アイコン・メッセージ
  const getStatusStyle = (): {
    bgColor: string;
    borderColor: string;
    textColor: string;
    icon: React.JSX.Element;
    message: string;
  } => {
    switch (readinessStatus) {
      case 'ready':
        return {
          bgColor: 'bg-green-50',
          borderColor: 'border-green-200',
          textColor: 'text-green-800',
          icon: (
            <svg className="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          ),
          message: 'リリース可能',
        };
      case 'warning':
        return {
          bgColor: 'bg-yellow-50',
          borderColor: 'border-yellow-200',
          textColor: 'text-yellow-800',
          icon: (
            <svg className="w-5 h-5 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          ),
          message: 'リリース可能（注意あり）',
        };
      case 'blocked':
        return {
          bgColor: 'bg-red-50',
          borderColor: 'border-red-200',
          textColor: 'text-red-800',
          icon: (
            <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          ),
          message: 'リリース不可',
        };
    }
  };

  const statusStyle = getStatusStyle();

  // リリース不可理由を取得
  const getBlockedReasons = (): string[] => {
    const reasons: string[] = [];
    const incompleteTasks = tasks.filter(
      t => t.status !== 'COMPLETED' && t.status !== 'DONE'
    );
    if (incompleteTasks.length > 0) {
      reasons.push(`未完了タスク: ${incompleteTasks.map(t => t.id).join(', ')}`);
    }
    if (needsReview) {
      const reviewTasks = tasks.filter(t => t.status === 'DONE');
      reasons.push(`レビュー待ち: ${reviewTasks.map(t => t.id).join(', ')}`);
    }
    return reasons;
  };

  const blockedReasons = getBlockedReasons();

  // TASK_132: リリース情報・関連情報を取得（ArtifactsBrowserから移設）
  useEffect(() => {
    const fetchMetaInfo = async () => {
      setMetaLoading(true);
      try {
        const [releaseResult, relatedResult] = await Promise.all([
          window.electronAPI.getOrderReleaseInfo(projectName, orderId),
          window.electronAPI.getOrderRelatedInfo(projectName, orderId),
        ]);
        setReleaseInfo(releaseResult);
        setRelatedInfo(relatedResult);
      } catch (err) {
        console.error('[ReleaseReadinessPanel] Failed to fetch meta info:', err);
        setReleaseInfo({ hasRelease: false, releases: [] });
        setRelatedInfo({ relatedBacklogs: [], dependentOrders: [] });
      } finally {
        setMetaLoading(false);
      }
    };

    fetchMetaInfo();
  }, [projectName, orderId]);

  // REPORTサマリを取得
  useEffect(() => {
    const fetchReportSummaries = async () => {
      setLoading(true);
      setError(null);
      try {
        // REPORTファイル一覧を取得
        const reportList = await window.electronAPI.getOrderReportList(projectName, orderId);
        if (!reportList || reportList.length === 0) {
          setReportSummaries([]);
          return;
        }

        // 各REPORTファイルを読み込み、変更ファイルとサマリを抽出
        const summaries: ReportSummary[] = [];
        for (const reportFilename of reportList) {
          try {
            const result = await window.electronAPI.getOrderReport(
              projectName,
              orderId,
              reportFilename
            );
            if (result.exists && result.content) {
              // タスクIDを抽出（REPORT_1148.md → TASK_1148）
              const taskIdMatch = reportFilename.match(/REPORT_(\d+)\.md$/);
              const taskId = taskIdMatch ? `TASK_${taskIdMatch[1]}` : 'UNKNOWN';

              // タスク情報を取得
              const task = tasks.find(t => t.id === taskId);
              const title = task?.title || '';

              // 変更ファイルを抽出（## 成果物 or ## 変更ファイル セクションから）
              const changedFiles = extractChangedFiles(result.content);

              // サマリを抽出（## 実行結果 or ## 作業サマリ セクションから）
              const summary = extractSummary(result.content);

              summaries.push({
                taskId,
                title,
                status: task?.status || 'UNKNOWN',
                changedFiles,
                summary,
              });
            }
          } catch (err) {
            console.error(`[ReleaseReadinessPanel] Failed to fetch report ${reportFilename}:`, err);
          }
        }

        setReportSummaries(summaries);
      } catch (err) {
        console.error('[ReleaseReadinessPanel] Failed to fetch report summaries:', err);
        setError('レポートサマリの取得に失敗しました');
      } finally {
        setLoading(false);
      }
    };

    fetchReportSummaries();
  }, [projectName, orderId, tasks]);

  // ORDER_017 / TASK_053: リリースノート生成
  const handleGenerateReleaseNote = useCallback(async (dryRun = false) => {
    setReleaseNoteLoading(true);
    setReleaseNoteError(null);
    try {
      const result = await window.electronAPI.generateReleaseNote(projectName, orderId, dryRun);
      if (result.success && result.noteContent) {
        setReleaseNoteContent(result.noteContent);
        setReleaseNoteExpanded(true);
      } else {
        setReleaseNoteError(result.error || 'リリースノートの生成に失敗しました');
      }
    } catch (err) {
      console.error('[ReleaseReadinessPanel] generateReleaseNote failed:', err);
      setReleaseNoteError('リリースノートの生成中にエラーが発生しました');
    } finally {
      setReleaseNoteLoading(false);
    }
  }, [projectName, orderId]);

  // ORDER_017 / TASK_053: 全タスクCOMPLETED時に自動生成
  useEffect(() => {
    if (allTasksCompleted && !autoFetchedRef.current && !releaseNoteContent) {
      autoFetchedRef.current = true;
      handleGenerateReleaseNote(false);
    }
  }, [allTasksCompleted, releaseNoteContent, handleGenerateReleaseNote]);

  // 変更ファイルをMarkdownから抽出
  const extractChangedFiles = (content: string): string[] => {
    const lines = content.split('\n');
    const files: string[] = [];
    let inArtifactsSection = false;

    for (const line of lines) {
      // 成果物・変更ファイルセクションを検出
      if (line.match(/^##\s+(成果物|変更ファイル|変更ファイル一覧|artifacts)/i)) {
        inArtifactsSection = true;
        continue;
      }
      // 次のセクションで終了
      if (inArtifactsSection && line.match(/^##\s+/)) {
        break;
      }
      // ファイルパスを抽出（- で始まる行 or バッククォートで囲まれた行）
      if (inArtifactsSection) {
        const fileMatch = line.match(/^[-*]\s+`?(.+?\.(?:tsx?|jsx?|py|md|json|ya?ml))`?/i);
        if (fileMatch) {
          files.push(fileMatch[1].trim());
        }
      }
    }

    return files;
  };

  // サマリをMarkdownから抽出
  const extractSummary = (content: string): string => {
    const lines = content.split('\n');
    let inSummarySection = false;
    const summaryLines: string[] = [];

    for (const line of lines) {
      // サマリセクションを検出
      if (line.match(/^##\s+(実行結果|実施内容|作業サマリ|summary)/i)) {
        inSummarySection = true;
        continue;
      }
      // 次のセクションで終了
      if (inSummarySection && line.match(/^##\s+/)) {
        break;
      }
      // サマリを収集（空行・JSONブロックは除外）
      if (inSummarySection && line.trim() && !line.match(/^```/)) {
        summaryLines.push(line.trim());
      }
    }

    // 最大3行まで表示
    return summaryLines.slice(0, 3).join(' ').substring(0, 200);
  };

  // 全変更ファイルのユニークリスト
  const allChangedFiles = Array.from(
    new Set(reportSummaries.flatMap(r => r.changedFiles))
  );

  // 影響範囲を推定（ファイルパスから）
  const getAffectedModules = (): string[] => {
    const modules = new Set<string>();
    for (const file of allChangedFiles) {
      // src/components/Foo.tsx → components
      // src/main/services/Bar.ts → services
      const match = file.match(/src\/([\w-]+)\//);
      if (match) {
        modules.add(match[1]);
      }
    }
    return Array.from(modules);
  };

  const affectedModules = getAffectedModules();

  // セクション用アイコン定義
  const icons = {
    task: (
      <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
    files: (
      <svg className="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    scope: (
      <svg className="w-4 h-4 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
      </svg>
    ),
    report: (
      <svg className="w-4 h-4 text-teal-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    note: (
      <svg className="w-4 h-4 text-violet-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
    release: (
      <svg className="w-4 h-4 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    related: (
      <svg className="w-4 h-4 text-pink-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
      </svg>
    ),
  };

  return (
    <div className="space-y-3">
      {/* リリース判定ステータスカード（常時表示） */}
      <div
        className={`rounded-lg border-l-4 border p-4 shadow-sm ${statusStyle.bgColor} ${statusStyle.borderColor}`}
      >
        <div className="flex items-center gap-3">
          <div className="flex-shrink-0">{statusStyle.icon}</div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className={`text-base font-bold ${statusStyle.textColor}`}>
                {statusStyle.message}
              </h3>
              {/* TASK_132: リリースバージョン情報統合 */}
              {!metaLoading && releaseInfo?.hasRelease && releaseInfo.latestVersion && (
                <span className="px-2 py-0.5 bg-green-100 text-green-800 text-xs rounded-full">
                  {releaseInfo.latestVersion}
                </span>
              )}
              {!metaLoading && releaseInfo?.hasRelease && (
                <span className="text-xs text-gray-500">
                  最終: {releaseInfo.releases[0]?.date}
                </span>
              )}
            </div>
            {blockedReasons.length > 0 && (
              <ul className="mt-1 text-xs text-red-700 space-y-0.5">
                {blockedReasons.map((reason, i) => (
                  <li key={i} className="flex items-start">
                    <span className="mr-1">-</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            )}
            {readinessStatus === 'warning' && (
              <p className="mt-1 text-xs text-yellow-700">
                REWORK履歴があります。リリース前に変更内容を再確認してください。
              </p>
            )}
          </div>
          {/* リリースボタン */}
          {shouldShowReleaseButton && (
            <button
              onClick={onExecuteRelease}
              disabled={(readinessStatus !== 'ready' && readinessStatus !== 'warning') || isReleaseRunning}
              title={
                readinessStatus === 'ready'
                  ? 'リリース処理を実行'
                  : readinessStatus === 'warning'
                  ? 'リリース可能（注意あり） - クリックして実行'
                  : 'リリース不可 - 下記の理由を確認してください'
              }
              className={`
                flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors flex-shrink-0
                ${
                  isReleaseRunning
                    ? 'bg-blue-100 text-blue-600 cursor-wait'
                    : readinessStatus === 'ready'
                    ? 'bg-purple-600 text-white hover:bg-purple-700'
                    : readinessStatus === 'warning'
                    ? 'bg-yellow-600 text-white hover:bg-yellow-700'
                    : 'bg-gray-200 text-gray-400 cursor-not-allowed'
                }
              `}
            >
              {isReleaseRunning ? (
                <>
                  <svg className="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>リリース中...</span>
                </>
              ) : (
                <>
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>リリース実行</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* タスク完了状況（常時表示・コンパクト） */}
      <div className="bg-white border border-gray-200 rounded-lg p-4 shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-gray-400">{icons.task}</span>
          <span className="text-sm font-semibold text-gray-700">タスク完了状況</span>
          <div className="flex-1 flex items-center gap-2">
            <div className="flex-1 h-2.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  allTasksCompleted ? 'bg-green-500' : 'bg-blue-500'
                }`}
                style={{ width: `${totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0}%` }}
              />
            </div>
            <span className="text-sm font-bold text-gray-900 whitespace-nowrap tabular-nums">
              {completedTasks}/{totalTasks}
            </span>
            <span className="text-xs text-gray-400 tabular-nums">
              ({totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0}%)
            </span>
          </div>
        </div>
        {doneTasks > 0 && (
          <p className="mt-2 text-xs text-yellow-700 bg-yellow-50 border border-yellow-200 rounded px-3 py-1.5 ml-7">
            {doneTasks}件のタスクがレビュー待ちです
          </p>
        )}
      </div>

      {/* TASK_132: リリース履歴情報（ArtifactsBrowserから移設、折りたたみ） */}
      {!metaLoading && releaseInfo?.hasRelease && (
        <CollapsibleSection
          title="リリース履歴"
          icon={icons.release}
          badge={`${releaseInfo.releases.length}回`}
        >
          <div className="mt-3 space-y-1.5">
            {releaseInfo.releases.map((release, idx) => (
              <div
                key={release.releaseId}
                className={`flex items-center justify-between py-2 px-3 rounded-md text-xs ${
                  idx % 2 === 0 ? 'bg-gray-50' : 'bg-white'
                } border border-gray-100`}
              >
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-gray-800">{release.releaseId}</span>
                  <span className="text-gray-400">{release.date}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-gray-500">{release.fileCount}ファイル</span>
                  <span className="text-gray-400 italic">by {release.executor}</span>
                </div>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* 変更ファイル一覧（折りたたみ） */}
      <CollapsibleSection
        title="変更ファイル"
        icon={icons.files}
        badge={allChangedFiles.length > 0 ? `${allChangedFiles.length}件` : undefined}
      >
        <div className="mt-3">
          {loading ? (
            <div className="text-xs text-gray-500 py-2">読み込み中...</div>
          ) : error ? (
            <div className="text-xs text-red-600 bg-red-50 rounded px-3 py-2">{error}</div>
          ) : allChangedFiles.length > 0 ? (
            <div className="max-h-40 overflow-y-auto rounded-md border border-gray-100">
              {allChangedFiles.map((file, i) => (
                <div
                  key={i}
                  className={`text-xs text-gray-600 font-mono px-3 py-1.5 ${
                    i % 2 === 0 ? 'bg-gray-50' : 'bg-white'
                  } ${i < allChangedFiles.length - 1 ? 'border-b border-gray-50' : ''}`}
                >
                  {file}
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-gray-400 py-2">変更ファイル情報がありません</div>
          )}
        </div>
      </CollapsibleSection>

      {/* 影響範囲（折りたたみ、モジュールがある場合のみ表示） */}
      {affectedModules.length > 0 && (
        <CollapsibleSection
          title="影響範囲"
          icon={icons.scope}
          badge={affectedModules.length}
        >
          <div className="mt-3 flex flex-wrap gap-2">
            {affectedModules.map((module) => (
              <span
                key={module}
                className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-blue-400 mr-1.5" />
                {module}
              </span>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* REPORTサマリ（折りたたみ） */}
      {reportSummaries.length > 0 && (
        <CollapsibleSection
          title="タスクレポート"
          icon={icons.report}
          badge={`${reportSummaries.length}件`}
        >
          <div className="mt-3 space-y-2">
            {reportSummaries.map((report) => (
              <div key={report.taskId} className="border-l-4 border-blue-300 pl-3 py-2 bg-gray-50 rounded-r-md">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-gray-800 bg-white px-1.5 py-0.5 rounded border border-gray-200">{report.taskId}</span>
                  {report.title && (
                    <span className="text-xs text-gray-600 truncate">{report.title}</span>
                  )}
                </div>
                {report.summary && (
                  <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">{report.summary}</p>
                )}
                {report.changedFiles.length > 0 && (
                  <div className="mt-1 text-xs text-gray-400">
                    変更: {report.changedFiles.length}ファイル
                  </div>
                )}
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      {/* TASK_132: 関連情報（ArtifactsBrowserから移設、折りたたみ） */}
      {!metaLoading && relatedInfo && (relatedInfo.relatedBacklogs.length > 0 || relatedInfo.dependentOrders.length > 0) && (
        <CollapsibleSection
          title="関連情報"
          icon={icons.related}
        >
          <div className="mt-3 space-y-3">
            {relatedInfo.relatedBacklogs.length > 0 && (
              <div>
                <span className="text-xs text-gray-500 font-semibold uppercase tracking-wider">関連バックログ ({relatedInfo.relatedBacklogs.length})</span>
                <div className="mt-1.5 space-y-1">
                  {relatedInfo.relatedBacklogs.map((backlog) => (
                    <div key={backlog.id} className="flex items-center justify-between text-xs py-1.5 px-2 rounded hover:bg-gray-50 transition-colors">
                      <div className="flex items-center min-w-0">
                        <span className="font-mono text-blue-600 font-semibold mr-2 flex-shrink-0">{backlog.id}</span>
                        <span className="text-gray-600 truncate">{backlog.title}</span>
                      </div>
                      <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs font-medium ml-2 flex-shrink-0">
                        {backlog.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {relatedInfo.dependentOrders.length > 0 && (
              <div>
                <span className="text-xs text-gray-500 font-semibold uppercase tracking-wider">依存ORDER ({relatedInfo.dependentOrders.length})</span>
                <div className="mt-1.5 space-y-1">
                  {relatedInfo.dependentOrders.map((order) => (
                    <div key={order.id} className="flex items-center justify-between text-xs py-1.5 px-2 rounded hover:bg-gray-50 transition-colors">
                      <div className="flex items-center min-w-0">
                        <span className="font-mono text-purple-600 font-semibold mr-2 flex-shrink-0">{order.id}</span>
                        <span className="text-gray-600 truncate">{order.title}</span>
                      </div>
                      <span className="px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 text-xs font-medium ml-2 flex-shrink-0">
                        {order.status}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* ORDER_017 / TASK_053: リリースノートセクション */}
      <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center">
            <span className="text-gray-400">{icons.note}</span>
            <span className="text-sm font-semibold text-gray-700 ml-2">リリースノート</span>
            {allTasksCompleted && (
              <span className="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
                自動生成済み
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5">
            {/* オンデマンド生成ボタン */}
            <button
              onClick={() => handleGenerateReleaseNote(false)}
              disabled={releaseNoteLoading}
              title="リリースノートを生成（RESULT/ORDER_XXX/RELEASE_NOTE.md に保存）"
              className={`
                flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors
                ${releaseNoteLoading
                  ? 'bg-gray-100 text-gray-400 cursor-wait'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
                }
              `}
            >
              {releaseNoteLoading ? (
                <>
                  <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>生成中...</span>
                </>
              ) : (
                <>
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                  <span>{releaseNoteContent ? '再生成' : '生成'}</span>
                </>
              )}
            </button>
            {/* 展開/折りたたみボタン（コンテンツがある場合のみ） */}
            {releaseNoteContent && (
              <button
                onClick={() => setReleaseNoteExpanded(prev => !prev)}
                className="flex items-center gap-1 px-1.5 py-1 rounded text-xs text-gray-500 hover:bg-gray-100 transition-colors"
                title={releaseNoteExpanded ? '折りたたむ' : '展開する'}
              >
                <svg
                  className={`w-4 h-4 transition-transform ${releaseNoteExpanded ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            )}
          </div>
        </div>

        {/* エラー表示 */}
        {releaseNoteError && (
          <div className="mx-4 mb-3 text-xs text-red-600 bg-red-50 border border-red-200 rounded-md p-2.5">
            {releaseNoteError}
          </div>
        )}

        {/* リリースノートコンテンツ */}
        {releaseNoteContent ? (
          releaseNoteExpanded ? (
            <div className="mx-4 mb-4 border border-gray-200 rounded-md bg-gray-50 p-3 max-h-80 overflow-y-auto">
              <MarkdownViewer content={releaseNoteContent} />
            </div>
          ) : (
            <div className="mx-4 mb-3 text-xs text-gray-400 italic">
              折りたたまれています
            </div>
          )
        ) : !releaseNoteLoading && !releaseNoteError ? (
          <div className="mx-4 mb-3 text-xs text-gray-400">
            {allTasksCompleted
              ? '自動生成中...'
              : '「生成」ボタンをクリックしてリリースノートを作成できます'}
          </div>
        ) : null}
      </div>
    </div>
  );
};
