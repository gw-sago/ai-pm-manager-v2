/**
 * InfoPageDetail.tsx
 *
 * INFO_PAGESの詳細表示コンポーネント
 * 指定ページのMarkdownコンテンツをレンダリングし、「一覧に戻る」ボタンを提供する。
 *
 * ORDER_024 / TASK_074: フロントエンドにINFO_PAGESカード一覧UIを実装
 */

import React from 'react';
import { MarkdownViewer } from '../MarkdownViewer';
import type { InfoPage } from '../../preload';

interface InfoPageDetailProps {
  /** 表示するページのメタ情報 */
  page: InfoPage;
  /** ページのMarkdownコンテンツ */
  content: string;
  /** 一覧に戻るボタンクリック時のコールバック */
  onBack: () => void;
}

/**
 * InfoPageDetailコンポーネント
 *
 * 選択されたINFO_PAGESページのMarkdownコンテンツをレンダリングする。
 * 上部に「一覧に戻る」ボタンとページタイトルを表示する。
 */
export const InfoPageDetail: React.FC<InfoPageDetailProps> = ({ page, content, onBack }) => {
  return (
    <div className="bg-white rounded-lg shadow">
      {/* ヘッダー: 戻るボタン + ページタイトル */}
      <div className="flex items-center gap-2 p-4 border-b border-gray-200">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          一覧に戻る
        </button>
        <span className="text-sm text-gray-500 ml-2">/ {page.title}</span>
      </div>

      {/* Markdownコンテンツ */}
      <div className="p-6">
        <MarkdownViewer content={content} />
      </div>
    </div>
  );
};
