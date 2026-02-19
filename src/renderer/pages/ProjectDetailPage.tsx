/**
 * ProjectDetailPage.tsx
 *
 * プロジェクト詳細ページ - INFO_PAGESカード一覧と詳細表示を統合したページコンポーネント
 *
 * - INFO_PAGESが存在する場合: InfoPagesListでカード一覧表示 → カードクリックでInfoPageDetailに遷移
 * - INFO_PAGESが存在しない場合: PROJECT_INFO.mdをMarkdownで表示（フォールバック）
 *
 * ORDER_024 / TASK_074: フロントエンドにINFO_PAGESカード一覧UIを実装
 */

import React, { useState, useEffect, useCallback } from 'react';
import { InfoPagesList } from '../../components/InfoPages/InfoPagesList';
import { InfoPageDetail } from '../../components/InfoPages/InfoPageDetail';
import { MarkdownViewer } from '../../components/MarkdownViewer';
import type { InfoPage, InfoPagesIndex } from '../../preload';

interface ProjectDetailPageProps {
  /** プロジェクトID（プロジェクト名） */
  projectId: string;
}

type ViewState =
  | { mode: 'loading' }
  | { mode: 'list'; infoPages: InfoPagesIndex }
  | { mode: 'detail'; infoPages: InfoPagesIndex; page: InfoPage; content: string }
  | { mode: 'fallback'; content: string }
  | { mode: 'empty' }
  | { mode: 'error'; message: string };

/**
 * ProjectDetailPageコンポーネント
 *
 * INFO_PAGESカード一覧 → ページ詳細のナビゲーションを管理する。
 */
export const ProjectDetailPage: React.FC<ProjectDetailPageProps> = ({ projectId }) => {
  const [viewState, setViewState] = useState<ViewState>({ mode: 'loading' });

  // INFO_PAGESの存在確認 + フォールバック読み込み
  useEffect(() => {
    if (!projectId) return;

    let cancelled = false;

    const load = async () => {
      setViewState({ mode: 'loading' });

      try {
        const pages = await window.electronAPI.getInfoPages(projectId);
        if (cancelled) return;

        if (pages && pages.pages.length > 0) {
          setViewState({ mode: 'list', infoPages: pages });
        } else {
          // フォールバック: PROJECT_INFO.md
          const mdContent = await window.electronAPI.getProjectInfoFile(projectId);
          if (cancelled) return;

          if (mdContent) {
            setViewState({ mode: 'fallback', content: mdContent });
          } else {
            setViewState({ mode: 'empty' });
          }
        }
      } catch (err) {
        if (cancelled) return;
        console.error('[ProjectDetailPage] Failed to load project info:', err);
        setViewState({ mode: 'error', message: 'プロジェクト情報の読み込みに失敗しました' });
      }
    };

    load();
    return () => { cancelled = true; };
  }, [projectId]);

  // カード選択: ページコンテンツを読み込み詳細ビューに遷移
  const handlePageSelect = useCallback(async (pageId: string) => {
    if (viewState.mode !== 'list') return;

    const { infoPages } = viewState;
    const page = infoPages.pages.find(p => p.id === pageId);
    if (!page) return;

    setViewState({ mode: 'loading' });

    try {
      const content = await window.electronAPI.getInfoPageContent(projectId, pageId);
      if (content) {
        setViewState({ mode: 'detail', infoPages, page, content });
      } else {
        setViewState({ mode: 'error', message: 'ページコンテンツが見つかりません' });
      }
    } catch (err) {
      console.error(`[ProjectDetailPage] Failed to load page ${pageId}:`, err);
      setViewState({ mode: 'error', message: 'ページの読み込みに失敗しました' });
    }
  }, [viewState, projectId]);

  // 詳細ビューから一覧に戻る
  const handleBack = useCallback(() => {
    if (viewState.mode !== 'detail') return;
    setViewState({ mode: 'list', infoPages: viewState.infoPages });
  }, [viewState]);

  // ローディング
  if (viewState.mode === 'loading') {
    return (
      <div className="p-4">
        <div className="text-gray-500">読み込み中...</div>
      </div>
    );
  }

  // エラー
  if (viewState.mode === 'error') {
    return (
      <div className="p-4">
        <div className="text-gray-500">{viewState.message}</div>
      </div>
    );
  }

  // 情報未作成
  if (viewState.mode === 'empty') {
    return (
      <div className="p-4">
        <div className="text-gray-400 text-sm">プロジェクト情報がまだ作成されていません。</div>
      </div>
    );
  }

  // フォールバック: PROJECT_INFO.md
  if (viewState.mode === 'fallback') {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <MarkdownViewer content={viewState.content} />
      </div>
    );
  }

  // INFO_PAGES: ページ詳細
  if (viewState.mode === 'detail') {
    return (
      <InfoPageDetail
        page={viewState.page}
        content={viewState.content}
        onBack={handleBack}
      />
    );
  }

  // INFO_PAGES: カード一覧
  return (
    <div className="space-y-4 p-2">
      <InfoPagesList
        infoPages={viewState.infoPages}
        onPageSelect={handlePageSelect}
      />
    </div>
  );
};
