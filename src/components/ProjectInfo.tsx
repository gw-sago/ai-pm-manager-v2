/**
 * ProjectInfo Component
 *
 * プロジェクト情報表示コンポーネント
 * - INFO_PAGES が存在する場合: カード一覧 → ページコンテンツ表示
 * - INFO_PAGES が存在しない場合: PROJECT_INFO.md をMarkdownで表示（フォールバック）
 *
 * ORDER_002 / BACKLOG_002: プロジェクト情報の深化
 */

import React, { useState, useEffect, useCallback } from 'react';
import { MarkdownViewer } from './MarkdownViewer';
import { ProjectInfoGuidance } from './ProjectInfoGuidance';
import type { InfoPage, InfoPagesIndex } from '../preload';

interface ProjectInfoProps {
  projectId: string;
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

  return <>{iconMap[icon] || iconMap['info']}</>;
};

/**
 * プロジェクト情報表示コンポーネント
 */
export const ProjectInfo: React.FC<ProjectInfoProps> = ({ projectId }) => {
  const [infoPages, setInfoPages] = useState<InfoPagesIndex | null>(null);
  const [selectedPageId, setSelectedPageId] = useState<string | null>(null);
  const [pageContent, setPageContent] = useState<string | null>(null);
  const [fallbackContent, setFallbackContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isInfoEmpty, setIsInfoEmpty] = useState(false);

  // INFO_PAGESの存在確認 + フォールバック読み込み
  useEffect(() => {
    if (!projectId) return;

    const loadProjectInfo = async () => {
      setIsLoading(true);
      setError(null);
      setIsInfoEmpty(false);
      setSelectedPageId(null);
      setPageContent(null);

      try {
        // まずINFO_PAGESを試す
        const pages = await window.electronAPI.getInfoPages(projectId);
        if (pages && pages.pages.length > 0) {
          setInfoPages(pages);
          setFallbackContent(null);
        } else {
          // フォールバック: PROJECT_INFO.md
          setInfoPages(null);
          const mdContent = await window.electronAPI.getProjectInfoFile(projectId);
          if (mdContent) {
            setFallbackContent(mdContent);
          } else {
            setIsInfoEmpty(true);
          }
        }
      } catch (err) {
        console.error('[ProjectInfo] Failed to load project info:', err);
        setError('プロジェクト情報の読み込みに失敗しました');
      } finally {
        setIsLoading(false);
      }
    };

    loadProjectInfo();
  }, [projectId]);

  // ページコンテンツ読み込み
  const loadPageContent = useCallback(async (pageId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const content = await window.electronAPI.getInfoPageContent(projectId, pageId);
      if (content) {
        setSelectedPageId(pageId);
        setPageContent(content);
      } else {
        setError('ページコンテンツが見つかりません');
      }
    } catch (err) {
      console.error(`[ProjectInfo] Failed to load page ${pageId}:`, err);
      setError('ページの読み込みに失敗しました');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  // 戻るボタン
  const handleBack = useCallback(() => {
    setSelectedPageId(null);
    setPageContent(null);
    setError(null);
  }, []);

  // ローディング
  if (isLoading) {
    return (
      <div className="p-4">
        <div className="text-gray-500">読み込み中...</div>
      </div>
    );
  }

  // 情報未作成: ガイダンスUI表示
  if (isInfoEmpty && !infoPages && !fallbackContent) {
    return <ProjectInfoGuidance projectId={projectId} />;
  }

  // エラー
  if (error && !infoPages && !fallbackContent) {
    return (
      <div className="p-4">
        <div className="text-gray-500">{error}</div>
      </div>
    );
  }

  // フォールバック: PROJECT_INFO.md表示
  if (!infoPages && fallbackContent) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <MarkdownViewer content={fallbackContent} />
      </div>
    );
  }

  // INFO_PAGES: ページコンテンツ表示
  if (infoPages && selectedPageId && pageContent) {
    const selectedPage = infoPages.pages.find(p => p.id === selectedPageId);
    return (
      <div className="bg-white rounded-lg shadow">
        <div className="flex items-center gap-2 p-4 border-b border-gray-200">
          <button
            onClick={handleBack}
            className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            一覧に戻る
          </button>
          {selectedPage && (
            <span className="text-sm text-gray-500 ml-2">/ {selectedPage.title}</span>
          )}
        </div>
        {error && (
          <div className="p-4 text-red-500 text-sm">{error}</div>
        )}
        <div className="p-6">
          <MarkdownViewer content={pageContent} />
        </div>
      </div>
    );
  }

  // INFO_PAGES: カード一覧表示
  if (infoPages) {
    return (
      <div className="p-2">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {infoPages.pages.map((page) => (
            <button
              key={page.id}
              onClick={() => loadPageContent(page.id)}
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
      </div>
    );
  }

  return null;
};
