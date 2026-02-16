/**
 * ReleaseReadinessPanel - リリース判定情報表示パネル
 *
 * ORDER_134 / TASK_1148
 *
 * タスク完了状況、レビュー結果、変更ファイル一覧、影響範囲、REPORTサマリを表示し、
 * リリース可否を色（緑・黄・赤）で視覚的に判定できるUIを提供する。
 */

import React, { useEffect, useState } from 'react';
import type { TaskInfo } from '../preload';

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

  // TASK_1150: リリースボタンを表示すべきか（全タスクCOMPLETED時のみ）
  const shouldShowReleaseButton = allTasksCompleted;

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
            <svg className="w-6 h-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
            <svg className="w-6 h-6 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
            <svg className="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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

  return (
    <div className="space-y-4">
      {/* リリース判定ステータスカード */}
      <div
        className={`rounded-lg border-2 p-4 ${statusStyle.bgColor} ${statusStyle.borderColor}`}
      >
        <div className="flex items-center gap-3">
          {statusStyle.icon}
          <div className="flex-1">
            <h3 className={`text-lg font-semibold ${statusStyle.textColor}`}>
              {statusStyle.message}
            </h3>
            {blockedReasons.length > 0 && (
              <ul className="mt-2 text-sm text-red-700 space-y-1">
                {blockedReasons.map((reason, i) => (
                  <li key={i} className="flex items-start">
                    <span className="mr-2">•</span>
                    <span>{reason}</span>
                  </li>
                ))}
              </ul>
            )}
            {readinessStatus === 'warning' && (
              <p className="mt-2 text-sm text-yellow-700">
                REWORK履歴があります。リリース前に変更内容を再確認してください。
              </p>
            )}
          </div>
          {/* TASK_1150: リリースボタン - 全タスク完了時に表示、readyステータスのみ有効化 */}
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
                flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors
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
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>リリース中...</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span>リリース実行</span>
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* タスク完了状況 */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
          <svg className="w-5 h-5 mr-2 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
          タスク完了状況
        </h4>
        <div className="flex items-center gap-4">
          <div className="text-2xl font-bold text-gray-900">
            {completedTasks}/{totalTasks}
          </div>
          <div className="flex-1">
            <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all ${
                  allTasksCompleted ? 'bg-green-500' : 'bg-blue-500'
                }`}
                style={{ width: `${totalTasks > 0 ? (completedTasks / totalTasks) * 100 : 0}%` }}
              />
            </div>
          </div>
          <div className="text-sm text-gray-600">
            {totalTasks > 0 ? Math.round((completedTasks / totalTasks) * 100) : 0}%
          </div>
        </div>
        {doneTasks > 0 && (
          <p className="mt-2 text-xs text-yellow-700">
            {doneTasks}件のタスクがレビュー待ちです
          </p>
        )}
      </div>

      {/* 変更ファイル一覧 */}
      <div className="bg-white border border-gray-200 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
          <svg className="w-5 h-5 mr-2 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          変更ファイル ({allChangedFiles.length}件)
        </h4>
        {loading ? (
          <div className="text-sm text-gray-500">読み込み中...</div>
        ) : error ? (
          <div className="text-sm text-red-600">{error}</div>
        ) : allChangedFiles.length > 0 ? (
          <div className="max-h-48 overflow-y-auto space-y-1">
            {allChangedFiles.map((file, i) => (
              <div key={i} className="text-xs text-gray-600 font-mono bg-gray-50 px-2 py-1 rounded">
                {file}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-sm text-gray-400">変更ファイル情報がありません</div>
        )}
      </div>

      {/* 影響範囲 */}
      {affectedModules.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
            <svg className="w-5 h-5 mr-2 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21a4 4 0 01-4-4V5a2 2 0 012-2h4a2 2 0 012 2v12a4 4 0 01-4 4zm0 0h12a2 2 0 002-2v-4a2 2 0 00-2-2h-2.343M11 7.343l1.657-1.657a2 2 0 012.828 0l2.829 2.829a2 2 0 010 2.828l-8.486 8.485M7 17h.01" />
            </svg>
            影響範囲
          </h4>
          <div className="flex flex-wrap gap-2">
            {affectedModules.map((module) => (
              <span
                key={module}
                className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-700"
              >
                {module}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* REPORTサマリ */}
      {reportSummaries.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center">
            <svg className="w-5 h-5 mr-2 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            タスクレポート ({reportSummaries.length}件)
          </h4>
          <div className="space-y-3">
            {reportSummaries.map((report) => (
              <div key={report.taskId} className="border-l-4 border-blue-300 pl-3 py-2 bg-gray-50">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-semibold text-gray-700">{report.taskId}</span>
                  {report.title && (
                    <span className="text-xs text-gray-600">- {report.title}</span>
                  )}
                </div>
                {report.summary && (
                  <p className="text-xs text-gray-600 line-clamp-2">{report.summary}</p>
                )}
                {report.changedFiles.length > 0 && (
                  <div className="mt-1 text-xs text-gray-500">
                    変更: {report.changedFiles.length}ファイル
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
