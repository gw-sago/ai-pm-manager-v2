/**
 * RecommendedActions Component
 *
 * 推奨アクション（次のアクション）セクションを表示するコンポーネント
 * ActionGeneratorから取得したアクションをActionCardリストで表示
 *
 * TASK_026: 推奨アクションUIコンポーネント実装
 */

import React, { useState, useEffect } from 'react';
import { ActionCard, type RecommendedAction } from './ActionCard';
import type { ParsedState } from '../preload';

interface RecommendedActionsProps {
  projectName: string;
  state: ParsedState;
}

/**
 * 空状態表示コンポーネント
 */
const EmptyState: React.FC = () => {
  return (
    <div className="text-center py-6">
      <div className="inline-flex items-center justify-center w-12 h-12 bg-green-100 rounded-full mb-3">
        <svg
          className="w-6 h-6 text-green-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
      </div>
      <h3 className="text-sm font-medium text-gray-900 mb-1">
        すべて順調です
      </h3>
      <p className="text-xs text-gray-500">
        現在、推奨されるアクションはありません
      </p>
    </div>
  );
};

/**
 * コピーフィードバックコンポーネント（成功/失敗両対応）
 * TASK_027: クリップボードコピー機能実装
 */
interface CopyFeedbackProps {
  show: boolean;
  success: boolean;
  message: string;
}

const CopyFeedback: React.FC<CopyFeedbackProps> = ({ show, success, message }) => {
  if (!show) return null;

  return (
    <div
      className={`fixed bottom-4 right-4 px-4 py-2 rounded-lg shadow-lg flex items-center space-x-2 animate-fade-in-up z-50 ${
        success ? 'bg-gray-800 text-white' : 'bg-red-600 text-white'
      }`}
      role="alert"
      aria-live="polite"
    >
      {success ? (
        <svg
          className="w-4 h-4 text-green-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
      ) : (
        <svg
          className="w-4 h-4 text-white"
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
      )}
      <span className="text-sm">{message}</span>
    </div>
  );
};

/**
 * RecommendedActions Component
 *
 * 推奨アクションセクションを表示
 * - ActionGeneratorをIPC経由で呼び出してアクション取得
 * - ActionCardをリスト表示
 * - 空の場合のメッセージ表示
 */
export const RecommendedActions: React.FC<RecommendedActionsProps> = ({
  projectName,
  state,
}) => {
  const [actions, setActions] = useState<RecommendedAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCopyFeedback, setShowCopyFeedback] = useState(false);
  const [copySuccess, setCopySuccess] = useState(true);
  const [copyMessage, setCopyMessage] = useState('');

  // 推奨アクションを取得
  useEffect(() => {
    const fetchActions = async () => {
      setLoading(true);
      setError(null);

      try {
        // IPC経由で推奨アクションを取得
        const result = await window.electronAPI.getRecommendedActions(
          projectName,
          state
        );
        setActions(result);
      } catch (err) {
        console.error('[RecommendedActions] 取得エラー:', err);
        setError('推奨アクションの取得に失敗しました');
        setActions([]);
      } finally {
        setLoading(false);
      }
    };

    fetchActions();
  }, [projectName, state]);

  // コピーハンドラ（TASK_027: エラーハンドリング強化）
  const handleCopy = async (command: string) => {
    try {
      await navigator.clipboard.writeText(command);
      setCopySuccess(true);
      setCopyMessage('コピーしました');
      setShowCopyFeedback(true);

      // 2秒後にフィードバックを非表示
      setTimeout(() => {
        setShowCopyFeedback(false);
      }, 2000);
    } catch (err) {
      console.error('[RecommendedActions] コピーエラー:', err);
      setCopySuccess(false);
      setCopyMessage('コピーに失敗しました');
      setShowCopyFeedback(true);

      // エラー時も2秒後に非表示
      setTimeout(() => {
        setShowCopyFeedback(false);
      }, 2000);
    }
  };

  // ローディング中
  if (loading) {
    return (
      <div>
        <h3 className="text-sm font-semibold text-gray-800 mb-3">
          次のアクション
        </h3>
        <div className="flex items-center justify-center py-4">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
          <span className="ml-2 text-sm text-gray-500">読み込み中...</span>
        </div>
      </div>
    );
  }

  // エラー時
  if (error) {
    return (
      <div>
        <h3 className="text-sm font-semibold text-gray-800 mb-3">
          次のアクション
        </h3>
        <div className="text-center py-4">
          <div className="inline-flex items-center justify-center w-10 h-10 bg-red-100 rounded-full mb-2">
            <svg
              className="w-5 h-5 text-red-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </div>
          <p className="text-xs text-red-600">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* ヘッダー */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-800">
          次のアクション
        </h3>
        {actions.length > 0 && (
          <span className="text-xs text-gray-500">
            {actions.length}件の推奨
          </span>
        )}
      </div>

      {/* アクションリストまたは空状態 */}
      {actions.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-3">
          {actions.map((action) => (
            <ActionCard key={action.id} action={action} onCopy={handleCopy} />
          ))}
        </div>
      )}

      {/* コピーフィードバック（成功/失敗両対応） */}
      <CopyFeedback show={showCopyFeedback} success={copySuccess} message={copyMessage} />
    </div>
  );
};
