import React from 'react';
import type { ProjectHealthData } from '../preload';

interface ProjectHealthCardProps {
  /** プロジェクト健康状態データ */
  project: ProjectHealthData;
  /** カード選択状態 */
  isSelected?: boolean;
  /** クリック時のコールバック */
  onClick?: () => void;
}

/**
 * 健康状態に応じたインジケータとスタイルを返す
 */
const getHealthIndicator = (status: ProjectHealthData['status']): {
  emoji: string;
  bg: string;
  border: string;
  text: string;
  label: string;
} => {
  switch (status) {
    case 'healthy':
      return {
        emoji: '🟢',
        bg: 'bg-green-50',
        border: 'border-green-200',
        text: 'text-green-700',
        label: '正常',
      };
    case 'warning':
      return {
        emoji: '🟡',
        bg: 'bg-yellow-50',
        border: 'border-yellow-200',
        text: 'text-yellow-700',
        label: '警告',
      };
    case 'critical':
      return {
        emoji: '🔴',
        bg: 'bg-red-50',
        border: 'border-red-200',
        text: 'text-red-700',
        label: '危険',
      };
    default:
      return {
        emoji: '⚪',
        bg: 'bg-gray-50',
        border: 'border-gray-200',
        text: 'text-gray-700',
        label: '不明',
      };
  }
};

/**
 * 進捗率に応じた色を返す
 */
const getProgressColor = (rate: number): string => {
  if (rate >= 80) return 'bg-green-500';
  if (rate >= 50) return 'bg-blue-500';
  if (rate >= 30) return 'bg-yellow-500';
  return 'bg-red-500';
};

/**
 * 相対時間を計算して表示文字列を返す
 */
const formatRelativeTime = (dateString?: string): string => {
  if (!dateString) return '-';

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMinutes < 1) return 'たった今';
  if (diffMinutes < 60) return `${diffMinutes}分前`;
  if (diffHours < 24) return `${diffHours}時間前`;
  if (diffDays < 7) return `${diffDays}日前`;

  return date.toLocaleDateString('ja-JP', { month: 'short', day: 'numeric' });
};

/**
 * プロジェクト健康状態カードコンポーネント
 *
 * プロジェクトの健康状態をカード形式で表示します。
 * - 健康状態インジケータ（🟢🟡🔴）
 * - プロジェクト名、現在のORDER
 * - 進捗率プログレスバー
 * - エスカレーション数、レビュー待ち数
 * - 最終更新日時
 */
export const ProjectHealthCard: React.FC<ProjectHealthCardProps> = ({
  project,
  isSelected = false,
  onClick,
}) => {
  const health = getHealthIndicator(project.status);
  const progressColor = getProgressColor(project.completionRate);

  return (
    <button
      onClick={onClick}
      className={`
        w-full text-left p-4 rounded-lg border-2 transition-all duration-200
        ${health.bg} ${health.border}
        ${isSelected ? 'ring-2 ring-blue-400 ring-offset-2' : ''}
        ${onClick ? 'hover:shadow-md hover:scale-[1.02] cursor-pointer' : 'cursor-default'}
      `}
    >
      {/* ヘッダー: 健康状態 + プロジェクト名 */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xl" role="img" aria-label={health.label}>
            {health.emoji}
          </span>
          <div>
            <h3 className="font-semibold text-gray-900 text-sm">
              {project.projectName}
            </h3>
            {project.currentOrderTitle && (
              <p className="text-xs text-gray-500 truncate max-w-[180px]">
                {project.currentOrderId}: {project.currentOrderTitle}
              </p>
            )}
          </div>
        </div>
        {/* ステータスラベル */}
        <span className={`text-xs font-medium px-2 py-0.5 rounded ${health.text} ${health.bg}`}>
          {health.label}
        </span>
      </div>

      {/* 進捗バー */}
      <div className="mb-3">
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs text-gray-600">進捗率</span>
          <span className="text-xs font-semibold text-gray-900">
            {project.completionRate}%
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
          <div
            className={`h-2 ${progressColor} rounded-full transition-all duration-500`}
            style={{ width: `${project.completionRate}%` }}
          />
        </div>
        <div className="flex justify-end mt-0.5">
          <span className="text-[10px] text-gray-400">
            {project.completedTasks} / {project.totalTasks} タスク
          </span>
        </div>
      </div>

      {/* タスク状態サマリ */}
      <div className="grid grid-cols-4 gap-1 mb-3 text-center">
        <div className="bg-white/60 rounded p-1">
          <div className="text-xs font-bold text-blue-600">{project.inProgressTasks}</div>
          <div className="text-[10px] text-gray-500">進行中</div>
        </div>
        <div className="bg-white/60 rounded p-1">
          <div className="text-xs font-bold text-orange-600">{project.blockedTasks}</div>
          <div className="text-[10px] text-gray-500">ブロック</div>
        </div>
        <div className="bg-white/60 rounded p-1">
          <div className="text-xs font-bold text-yellow-600">{project.pendingReviews}</div>
          <div className="text-[10px] text-gray-500">レビュー</div>
        </div>
        <div className="bg-white/60 rounded p-1">
          <div className="text-xs font-bold text-red-600">{project.openEscalations}</div>
          <div className="text-[10px] text-gray-500">ESC</div>
        </div>
      </div>

      {/* 差戻しタスク警告（ある場合のみ） */}
      {project.reworkTasks > 0 && (
        <div className="flex items-center gap-1 mb-2 px-2 py-1 bg-orange-100 rounded text-orange-700">
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <span className="text-xs font-medium">差戻し {project.reworkTasks} 件</span>
        </div>
      )}

      {/* フッター: 最終更新日時 */}
      <div className="flex items-center justify-between pt-2 border-t border-gray-200/50">
        <span className="text-[10px] text-gray-400">最終更新</span>
        <span className="text-[10px] text-gray-500">
          {formatRelativeTime(project.lastActivity)}
        </span>
      </div>
    </button>
  );
};
