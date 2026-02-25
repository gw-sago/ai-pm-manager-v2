/**
 * OrderSuggestPanel - ORDER自動提案パネルコンポーネント
 *
 * AIによるORDER候補の自動提案と一括登録機能を提供します。
 * - 「自動提案」ボタンでORDER候補を生成
 * - 提案結果のリスト表示（タイトル・説明・優先度・カテゴリ・根拠）
 * - チェックボックスによる複数選択
 * - 「選択済みを登録」ボタンで一括登録
 * - ローディング状態・エラー表示
 *
 * @module OrderSuggestPanel
 * @created 2026-02-19
 * @order ORDER_020
 * @task TASK_063
 */

import React, { useState, useCallback } from 'react';
import type { OrderSuggestItem } from '../preload';

// =============================================================================
// 型定義
// =============================================================================

export interface OrderSuggestPanelProps {
  /** プロジェクトID */
  projectId: string;
  /** 一括登録完了時のコールバック */
  onComplete?: () => void;
}

// =============================================================================
// 定数
// =============================================================================

/** 優先度に対応する色クラス */
const PRIORITY_COLORS: Record<string, string> = {
  High: 'bg-red-100 text-red-700 border-red-200',
  Medium: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  Low: 'bg-green-100 text-green-700 border-green-200',
};

// =============================================================================
// メインコンポーネント
// =============================================================================

/**
 * ORDER自動提案パネル
 */
export const OrderSuggestPanel: React.FC<OrderSuggestPanelProps> = ({
  projectId,
  onComplete,
}) => {
  // --------------------------------------------------------------------------
  // 状態管理
  // --------------------------------------------------------------------------

  /** 提案候補リスト */
  const [suggestions, setSuggestions] = useState<OrderSuggestItem[]>([]);
  /** 選択済みインデックスのセット */
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  /** 提案ローディング状態 */
  const [isSuggesting, setIsSuggesting] = useState(false);
  /** 登録ローディング状態 */
  const [isRegistering, setIsRegistering] = useState(false);
  /** エラーメッセージ */
  const [error, setError] = useState<string | null>(null);
  /** 成功メッセージ */
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // --------------------------------------------------------------------------
  // イベントハンドラ
  // --------------------------------------------------------------------------

  /**
   * 自動提案ボタンクリックハンドラ
   */
  const handleSuggest = useCallback(async () => {
    setIsSuggesting(true);
    setError(null);
    setSuccessMessage(null);
    setSuggestions([]);
    setSelectedIndices(new Set());

    try {
      const result = await window.electronAPI.suggestOrders(projectId);
      if (result.success && result.suggestions) {
        setSuggestions(result.suggestions);
        if (result.suggestions.length === 0) {
          setError('提案が生成されませんでした。プロジェクト情報を確認してください。');
        }
      } else {
        setError(result.error || '提案の生成に失敗しました');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '提案の生成中にエラーが発生しました';
      setError(message);
      console.error('[OrderSuggestPanel] suggestOrders error:', err);
    } finally {
      setIsSuggesting(false);
    }
  }, [projectId]);

  /**
   * チェックボックス変更ハンドラ
   */
  const handleToggleSelect = useCallback((index: number) => {
    setSelectedIndices((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  /**
   * 全選択/全解除トグルハンドラ
   */
  const handleToggleAll = useCallback(() => {
    if (selectedIndices.size === suggestions.length) {
      setSelectedIndices(new Set());
    } else {
      setSelectedIndices(new Set(suggestions.map((_, i) => i)));
    }
  }, [selectedIndices.size, suggestions]);

  /**
   * 選択済みを登録ボタンクリックハンドラ
   */
  const handleBulkAdd = useCallback(async () => {
    if (selectedIndices.size === 0) return;

    const itemsToAdd = Array.from(selectedIndices).map((i) => ({
      title: suggestions[i].title,
      description: suggestions[i].description,
      priority: suggestions[i].priority,
      category: suggestions[i].category,
    }));

    setIsRegistering(true);
    setError(null);
    setSuccessMessage(null);

    try {
      const result = await window.electronAPI.bulkAddOrders(projectId, itemsToAdd);
      if (result.success) {
        const count = result.addedCount ?? itemsToAdd.length;
        setSuccessMessage(`${count}件のORDERを登録しました`);
        setSuggestions([]);
        setSelectedIndices(new Set());
        onComplete?.();
      } else {
        setError(result.error || 'ORDERの登録に失敗しました');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'ORDERの登録中にエラーが発生しました';
      setError(message);
      console.error('[OrderSuggestPanel] bulkAddOrders error:', err);
    } finally {
      setIsRegistering(false);
    }
  }, [selectedIndices, suggestions, projectId, onComplete]);

  // --------------------------------------------------------------------------
  // レンダリング
  // --------------------------------------------------------------------------

  const allSelected = suggestions.length > 0 && selectedIndices.size === suggestions.length;

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm">
      {/* ヘッダー */}
      <div className="flex items-center justify-between p-4 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
          <h3 className="font-medium text-gray-800">AI ORDER自動提案</h3>
        </div>
        <button
          onClick={handleSuggest}
          disabled={isSuggesting || isRegistering}
          className={`
            flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors
            ${isSuggesting || isRegistering
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-purple-600 text-white hover:bg-purple-700'
            }
          `}
        >
          {isSuggesting ? (
            <>
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span>提案を生成中...</span>
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              <span>自動提案</span>
            </>
          )}
        </button>
      </div>

      {/* エラー表示 */}
      {error && (
        <div className="mx-4 mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
          <div className="flex items-start gap-2">
            <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="text-sm text-red-700">{error}</p>
          </div>
        </div>
      )}

      {/* 成功メッセージ */}
      {successMessage && (
        <div className="mx-4 mt-4 p-3 bg-green-50 border border-green-200 rounded-lg">
          <div className="flex items-start gap-2">
            <svg className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <p className="text-sm text-green-700">{successMessage}</p>
          </div>
        </div>
      )}

      {/* 提案リスト */}
      {suggestions.length > 0 && (
        <div className="p-4">
          {/* 全選択コントロール */}
          <div className="flex items-center justify-between mb-3">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={allSelected}
                onChange={handleToggleAll}
                className="w-4 h-4 rounded border-gray-300 text-purple-600 focus:ring-purple-500"
              />
              <span className="text-sm text-gray-600">
                {allSelected ? '全て解除' : '全て選択'}（{selectedIndices.size}/{suggestions.length}件選択中）
              </span>
            </label>

            {/* 選択済みを登録ボタン */}
            <button
              onClick={handleBulkAdd}
              disabled={selectedIndices.size === 0 || isRegistering}
              className={`
                flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors
                ${selectedIndices.size === 0 || isRegistering
                  ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 text-white hover:bg-blue-700'
                }
              `}
            >
              {isRegistering ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  <span>登録中...</span>
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                  <span>選択済みを登録 ({selectedIndices.size}件)</span>
                </>
              )}
            </button>
          </div>

          {/* 提案カードリスト */}
          <div className="space-y-3">
            {suggestions.map((item, index) => (
              <SuggestionCard
                key={index}
                item={item}
                index={index}
                isSelected={selectedIndices.has(index)}
                onToggle={handleToggleSelect}
              />
            ))}
          </div>
        </div>
      )}

      {/* 空状態（提案なし、かつローディング中でもエラーでもない） */}
      {!isSuggesting && !error && suggestions.length === 0 && !successMessage && (
        <div className="p-8 text-center">
          <div className="w-12 h-12 bg-purple-50 rounded-full flex items-center justify-center mx-auto mb-3">
            <svg className="w-6 h-6 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </div>
          <p className="text-sm text-gray-500">
            「自動提案」ボタンをクリックすると、AIがプロジェクト情報を分析してORDER候補を提案します
          </p>
        </div>
      )}
    </div>
  );
};

// =============================================================================
// サブコンポーネント
// =============================================================================

interface SuggestionCardProps {
  item: OrderSuggestItem;
  index: number;
  isSelected: boolean;
  onToggle: (index: number) => void;
}

const SuggestionCard: React.FC<SuggestionCardProps> = ({ item, index, isSelected, onToggle }) => {
  const priorityColor = PRIORITY_COLORS[item.priority] || 'bg-gray-100 text-gray-600 border-gray-200';

  return (
    <div
      onClick={() => onToggle(index)}
      className={`
        p-4 rounded-lg border cursor-pointer transition-all
        ${isSelected
          ? 'border-purple-400 bg-purple-50 shadow-sm'
          : 'border-gray-200 bg-gray-50 hover:border-gray-300 hover:bg-white'
        }
      `}
    >
      <div className="flex items-start gap-3">
        {/* チェックボックス */}
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggle(index)}
          onClick={(e) => e.stopPropagation()}
          className="w-4 h-4 mt-0.5 rounded border-gray-300 text-purple-600 focus:ring-purple-500 flex-shrink-0"
        />

        {/* コンテンツ */}
        <div className="flex-1 min-w-0">
          {/* タイトルと優先度・カテゴリ */}
          <div className="flex items-start justify-between gap-2 mb-2">
            <h4 className="text-sm font-medium text-gray-900 flex-1">{item.title}</h4>
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {item.category && (
                <span className="inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded bg-gray-100 text-gray-600 border border-gray-200">
                  {item.category}
                </span>
              )}
              <span className={`inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded border ${priorityColor}`}>
                {item.priority}
              </span>
            </div>
          </div>

          {/* 説明 */}
          {item.description && (
            <p className="text-xs text-gray-600 mb-2 line-clamp-3">{item.description}</p>
          )}

          {/* 根拠 */}
          {item.rationale && (
            <div className="flex items-start gap-1.5 mt-2 pt-2 border-t border-gray-200">
              <svg className="w-3.5 h-3.5 text-purple-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <p className="text-[10px] text-purple-700 leading-relaxed">{item.rationale}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

// =============================================================================
// デフォルトエクスポート
// =============================================================================

export default OrderSuggestPanel;
