import React from 'react';
import type { TaskInfo } from '../preload';
import { TaskDependencyStatus, type TaskDependencyState } from './TaskDependencyStatus';

interface TaskCardProps {
  task: TaskInfo;
  onClick?: () => void;
  dependencyState?: TaskDependencyState | null;
}

/**
 * タスクステータスに応じた色定義
 */
const statusColors: Record<string, { bg: string; text: string; border: string }> = {
  QUEUED: {
    bg: 'bg-gray-100',
    text: 'text-gray-700',
    border: 'border-gray-300',
  },
  BLOCKED: {
    bg: 'bg-red-100',
    text: 'text-red-700',
    border: 'border-red-300',
  },
  IN_PROGRESS: {
    bg: 'bg-blue-100',
    text: 'text-blue-700',
    border: 'border-blue-300',
  },
  IN_REVIEW: {
    bg: 'bg-orange-100',
    text: 'text-orange-700',
    border: 'border-orange-300',
  },
  DONE: {
    bg: 'bg-yellow-100',
    text: 'text-yellow-700',
    border: 'border-yellow-300',
  },
  REWORK: {
    bg: 'bg-orange-100',
    text: 'text-orange-700',
    border: 'border-orange-300',
  },
  COMPLETED: {
    bg: 'bg-green-100',
    text: 'text-green-700',
    border: 'border-green-300',
  },
  CANCELLED: {
    bg: 'bg-gray-200',
    text: 'text-gray-500',
    border: 'border-gray-400',
  },
  REJECTED: {
    bg: 'bg-red-200',
    text: 'text-red-800',
    border: 'border-red-500',
  },
  SKIPPED: {
    bg: 'bg-gray-100',
    text: 'text-gray-400',
    border: 'border-gray-200',
  },
};

/**
 * ステータスアイコンコンポーネント
 */
const StatusIcon: React.FC<{ status: string }> = ({ status }) => {
  switch (status) {
    case 'COMPLETED':
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'IN_PROGRESS':
      return (
        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
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
      );
    case 'BLOCKED':
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M13.477 14.89A6 6 0 015.11 6.524l8.367 8.368zm1.414-1.414L6.524 5.11a6 6 0 018.367 8.367zM18 10a8 8 0 11-16 0 8 8 0 0116 0z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'DONE':
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
          <path
            fillRule="evenodd"
            d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm9.707 5.707a1 1 0 00-1.414-1.414L9 12.586l-1.293-1.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'REWORK':
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'IN_REVIEW':
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
        </svg>
      );
    case 'CANCELLED':
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'REJECTED':
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'SKIPPED':
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'QUEUED':
    default:
      return (
        <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
            clipRule="evenodd"
          />
        </svg>
      );
  }
};

/**
 * TASKカードコンポーネント
 *
 * タスクの情報をコンパクトなカード形式で表示します。
 * ステータスに応じた色分け、アイコン表示を行います。
 */
export const TaskCard: React.FC<TaskCardProps> = ({ task, onClick, dependencyState }) => {
  const colors = statusColors[task.status] || statusColors.QUEUED;

  return (
    <div
      className={`flex items-center justify-between p-3 rounded-lg border ${colors.border} ${colors.bg} transition-all duration-200 hover:shadow-sm cursor-pointer`}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onClick?.();
        }
      }}
    >
      {/* 左側: タスクID・タイトル */}
      <div className="flex items-center space-x-3 min-w-0 flex-1">
        {/* ステータスアイコン */}
        <div className={`flex-shrink-0 ${colors.text}`}>
          <StatusIcon status={task.status} />
        </div>

        {/* タスク情報 */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center space-x-2">
            <span className="text-xs font-mono text-gray-500">{task.id}</span>
            {/* 依存関係状態表示 */}
            <TaskDependencyStatus dependencyState={dependencyState ?? null} compact />
          </div>
          <div className="text-sm font-medium text-gray-900 truncate" title={task.title}>
            {task.title}
          </div>
        </div>
      </div>

      {/* 右側: ステータス・担当 */}
      <div className="flex items-center space-x-2 flex-shrink-0 ml-2">
        {/* 担当者 */}
        {task.assignee && task.assignee !== '-' && (
          <span className="text-xs text-gray-500 bg-gray-200 px-1.5 py-0.5 rounded">
            {task.assignee}
          </span>
        )}

        {/* ステータスバッジ */}
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors.bg} ${colors.text}`}
        >
          {task.status}
        </span>
      </div>
    </div>
  );
};
