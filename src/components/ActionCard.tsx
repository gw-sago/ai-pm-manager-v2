/**
 * ActionCard Component
 *
 * 推奨アクション（コマンド）を表示するカードコンポーネント
 *
 * TASK_026: 推奨アクションUIコンポーネント実装
 */

import React, { useState } from 'react';

/**
 * アクションタイプ
 */
export type ActionType = 'review' | 'worker' | 'status';

/**
 * 推奨アクション
 */
export interface RecommendedAction {
  id: string;
  type: ActionType;
  command: string;
  description: string;
  priority: number;
  taskId?: string;
}

interface ActionCardProps {
  action: RecommendedAction;
  onCopy: (command: string) => void;
}

/**
 * アクションタイプに対応するアイコンを返す
 */
const getActionIcon = (type: ActionType): string => {
  switch (type) {
    case 'review':
      return '📋';
    case 'worker':
      return '🔧';
    case 'status':
      return '📊';
    default:
      return '📌';
  }
};

/**
 * アクションタイプに対応するラベルを返す
 */
const getActionLabel = (type: ActionType): string => {
  switch (type) {
    case 'review':
      return 'レビュー';
    case 'worker':
      return 'Worker';
    case 'status':
      return 'ステータス';
    default:
      return '不明';
  }
};

/**
 * アクションタイプに対応する色クラスを返す
 */
const getActionColorClasses = (
  type: ActionType
): { bg: string; border: string; text: string } => {
  switch (type) {
    case 'review':
      return {
        bg: 'bg-yellow-50',
        border: 'border-yellow-200',
        text: 'text-yellow-700',
      };
    case 'worker':
      return {
        bg: 'bg-blue-50',
        border: 'border-blue-200',
        text: 'text-blue-700',
      };
    case 'status':
      return {
        bg: 'bg-gray-50',
        border: 'border-gray-200',
        text: 'text-gray-700',
      };
    default:
      return {
        bg: 'bg-gray-50',
        border: 'border-gray-200',
        text: 'text-gray-700',
      };
  }
};

/**
 * ActionCard Component
 *
 * 推奨アクションをカード形式で表示
 * - アイコン（type別）
 * - コマンド文字列（monospace）
 * - 説明テキスト
 * - コピーボタン
 */
export const ActionCard: React.FC<ActionCardProps> = ({ action, onCopy }) => {
  const [copied, setCopied] = useState(false);
  const icon = getActionIcon(action.type);
  const label = getActionLabel(action.type);
  const colors = getActionColorClasses(action.type);

  // ORDER_100 TASK_967: IN_PROGRESS再実行の検出
  const isRetry = action.id.startsWith('retry-');

  const handleCopyClick = () => {
    onCopy(action.command);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div
      className={`rounded-lg border ${isRetry ? 'border-orange-300 bg-orange-50' : `${colors.border} ${colors.bg}`} p-4 transition-all duration-200 hover:shadow-md`}
      role="article"
      aria-label={`推奨アクション: ${action.description}`}
    >
      <div className="flex items-start justify-between">
        {/* 左側: アイコンとコンテンツ */}
        <div className="flex items-start space-x-3 flex-1 min-w-0">
          {/* アイコン */}
          <div
            className="flex-shrink-0 text-2xl"
            role="img"
            aria-label={isRetry ? 'Retry' : label}
          >
            {isRetry ? '🔄' : icon}
          </div>

          {/* コンテンツ */}
          <div className="flex-1 min-w-0">
            {/* コマンド */}
            <code
              className={`block font-mono text-sm ${isRetry ? 'text-orange-700' : colors.text} bg-white/50 rounded px-2 py-1 truncate`}
              title={action.command}
            >
              {action.command}
            </code>

            {/* 説明 */}
            <p className={`mt-1 text-sm ${isRetry ? 'text-orange-600' : 'text-gray-600'} truncate`}>
              {action.description}
            </p>
          </div>
        </div>

        {/* 右側: コピーボタン（アイコン変化方式） */}
        <button
          onClick={handleCopyClick}
          disabled={copied}
          className={`flex-shrink-0 ml-3 px-3 py-1.5 text-xs font-medium rounded-md focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-blue-500 transition-all duration-150 ${
            copied
              ? 'text-green-600 bg-green-50 border border-green-300 cursor-default'
              : isRetry
              ? 'text-orange-600 bg-orange-100 border border-orange-300 hover:bg-orange-200'
              : 'text-gray-600 bg-white border border-gray-300 hover:bg-gray-50 hover:border-gray-400'
          }`}
          title={copied ? 'コピーしました' : `コマンドをコピー: ${action.command}`}
          aria-label={copied ? 'コピーしました' : `コマンド「${action.command}」をクリップボードにコピー`}
        >
          {copied ? '✓ Copied' : isRetry ? '🔄 Retry' : '📋 Copy'}
        </button>
      </div>
    </div>
  );
};
