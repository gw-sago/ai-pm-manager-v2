/**
 * ProjectInfo Component
 *
 * プロジェクト情報表示コンポーネント
 * - INFO_PAGES が存在する場合: カード一覧 → ページコンテンツ表示
 * - INFO_PAGES が存在しない場合: PROJECT_INFO.md をMarkdownで表示（フォールバック）
 *
 * ORDER_002: プロジェクト情報の深化
 */

import React, { useState, useEffect, useCallback } from 'react';
import { MarkdownViewer } from './MarkdownViewer';
import { ProjectInfoGuidance } from './ProjectInfoGuidance';
import { ProjectPageGenerator } from './ProjectPageGenerator';
import type { InfoPagesIndex } from '../preload';

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
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isRefreshingDirect, setIsRefreshingDirect] = useState(false);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // トースト自動消去
  useEffect(() => {
    if (toast) {
      const timer = setTimeout(() => setToast(null), 5000);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [toast]);

  // プロジェクト情報をロード（初回＋リフレッシュ後の再取得に使用）
  const loadProjectInfo = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setIsInfoEmpty(false);
    setSelectedPageId(null);
    setPageContent(null);

    try {
      const pages = await window.electronAPI.getInfoPages(projectId);
      if (pages && pages.pages.length > 0) {
        setInfoPages(pages);
        setFallbackContent(null);
      } else {
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
  }, [projectId]);

  // INFO_PAGESの存在確認 + フォールバック読み込み
  useEffect(() => {
    if (!projectId) return;
    loadProjectInfo();
  }, [projectId, loadProjectInfo]);

  // PROJECT_INFO.md最新化DRAFT ORDER追加ハンドラ
  const handleAddOrderItem = useCallback(async () => {
    setIsRefreshing(true);
    setToast(null);
    try {
      const result = await window.electronAPI.createDraftOrder(
        projectId,
        'PROJECT_INFO.md の最新化',
        'プロジェクト情報（PROJECT_INFO.md）を最新の状態に更新してください。',
        'Medium',
        undefined
      );
      if (result.success) {
        setToast({ type: 'success', message: 'DRAFT ORDERに追加しました' });
      } else {
        setToast({ type: 'error', message: result.error || 'DRAFT ORDERへの追加に失敗しました' });
      }
    } catch (err) {
      console.error('[ProjectInfo] Failed to add order item:', err);
      setToast({ type: 'error', message: 'DRAFT ORDER追加中にエラーが発生しました' });
    } finally {
      setIsRefreshing(false);
    }
  }, [projectId]);

  // プロジェクト情報をAIで直接最新化するハンドラ
  const handleRefreshDirect = useCallback(async () => {
    setIsRefreshingDirect(true);
    setToast(null);
    try {
      const result = await window.electronAPI.refreshProjectInfo(projectId);
      if (result.success) {
        setToast({ type: 'success', message: result.message || 'プロジェクト情報を最新化しました' });
        await loadProjectInfo();
      } else {
        setToast({ type: 'error', message: result.error || 'プロジェクト情報の最新化に失敗しました' });
      }
    } catch (err) {
      console.error('[ProjectInfo] Failed to refresh project info directly:', err);
      setToast({ type: 'error', message: 'プロジェクト情報の最新化中にエラーが発生しました' });
    } finally {
      setIsRefreshingDirect(false);
    }
  }, [projectId, loadProjectInfo]);

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

  // 最新化リクエストボタンUI（共通）
  const refreshButton = (
    <button
      onClick={handleAddOrderItem}
      disabled={isRefreshing}
      className={`inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
        isRefreshing
          ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
          : 'bg-blue-50 text-blue-600 hover:bg-blue-100 border border-blue-200'
      }`}
      title="PROJECT_INFO.md 最新化のバックログを追加します"
    >
      {isRefreshing ? (
        <>
          <svg className="animate-spin -ml-0.5 mr-1.5 h-4 w-4" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          追加中...
        </>
      ) : (
        <>
          <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          最新化リクエスト
        </>
      )}
    </button>
  );

  // AI直接実行ボタンUI（共通）
  const refreshDirectButton = (
    <button
      onClick={handleRefreshDirect}
      disabled={isRefreshingDirect}
      className={`inline-flex items-center px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
        isRefreshingDirect
          ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
          : 'bg-purple-50 text-purple-600 hover:bg-purple-100 border border-purple-200'
      }`}
      title="AIがプロジェクト情報を今すぐ最新化します"
    >
      {isRefreshingDirect ? (
        <>
          <svg className="animate-spin -ml-0.5 mr-1.5 h-4 w-4" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          最新化中...
        </>
      ) : (
        <>
          <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          プロジェクト情報を最新化
        </>
      )}
    </button>
  );

  // トーストUI（共通）
  const toastUI = toast && (
    <div className={`fixed bottom-4 right-4 z-50 flex items-center px-4 py-3 rounded-lg shadow-lg ${
      toast.type === 'success' ? 'bg-green-600 text-white' : 'bg-red-600 text-white'
    }`}>
      <svg className="w-5 h-5 mr-2 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        {toast.type === 'success' ? (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        ) : (
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        )}
      </svg>
      <span className="text-sm font-medium">{toast.message}</span>
      <button onClick={() => setToast(null)} className="ml-4 text-white hover:text-gray-200">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );

  // フォールバック: PROJECT_INFO.md表示
  if (!infoPages && fallbackContent) {
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-end gap-2 px-2">
          {refreshDirectButton}
          {refreshButton}
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <MarkdownViewer content={fallbackContent} />
        </div>
        <ProjectPageGenerator projectId={projectId} />
        {toastUI}
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
      <div className="space-y-4 p-2">
        <div className="flex items-center justify-end gap-2">
          {refreshDirectButton}
          {refreshButton}
        </div>
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
        <ProjectPageGenerator projectId={projectId} />
        {toastUI}
      </div>
    );
  }

  return null;
};
