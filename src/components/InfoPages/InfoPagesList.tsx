/**
 * InfoPagesList.tsx
 *
 * INFO_PAGESのカード一覧UIコンポーネント
 * index.jsonを読み込んでカードグリッドを表示する。
 * カードクリック時はonPageSelectコールバックでページIDを通知する。
 *
 * ORDER_024 / TASK_074: フロントエンドにINFO_PAGESカード一覧UIを実装
 */

import React from 'react';
import type { InfoPage, InfoPagesIndex } from '../../preload';

interface InfoPagesListProps {
  /** INFO_PAGESインデックスデータ */
  infoPages: InfoPagesIndex;
  /** カードクリック時のコールバック */
  onPageSelect: (pageId: string) => void;
}

/** アイコン名からSVGを返すヘルパー */
const PageIcon: React.FC<{ icon: string; className?: string }> = ({ icon, className = 'w-6 h-6' }) => {
  const iconMap: Record<string, React.ReactNode> = {
    info: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    cpu: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
    folder: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
      </svg>
    ),
    'file-text': (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    'check-square': (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
    shield: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
      </svg>
    ),
    book: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
      </svg>
    ),
  };

  return <>{iconMap[icon] ?? iconMap['info']}</>;
};

/**
 * InfoPagesListコンポーネント
 *
 * INFO_PAGESのindex.jsonを受け取り、カードグリッドとして表示する。
 * 各カードクリック時にonPageSelectでページIDを通知する。
 */
export const InfoPagesList: React.FC<InfoPagesListProps> = ({ infoPages, onPageSelect }) => {
  if (!infoPages.pages || infoPages.pages.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400">
        <p>表示するページがありません</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {infoPages.pages.map((page: InfoPage) => (
        <button
          key={page.id}
          onClick={() => onPageSelect(page.id)}
          className="bg-white rounded-lg shadow hover:shadow-md transition-shadow p-5 text-left border border-gray-100 hover:border-blue-200 group"
        >
          <div className="flex items-start gap-3">
            <div className="text-gray-400 group-hover:text-blue-500 transition-colors mt-0.5">
              <PageIcon icon={page.icon} />
            </div>
            <div className="min-w-0 flex-1">
              <h3 className="font-medium text-gray-900 group-hover:text-blue-600 transition-colors text-sm">
                {page.title}
              </h3>
              <p className="text-xs text-gray-500 mt-1 line-clamp-2">
                {page.description}
              </p>
            </div>
          </div>
        </button>
      ))}
    </div>
  );
};
