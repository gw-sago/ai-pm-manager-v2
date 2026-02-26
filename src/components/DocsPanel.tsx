/**
 * DocsPanel.tsx - ドキュメントツリービュー & マルチフォーマットビューア
 *
 * プロジェクト設定に基づくドキュメントをツリー表示し、
 * 選択したファイルの内容をビューアで表示する。
 * dev_workspace_path設定時はプロジェクトフォルダを、未設定時はdocs/を参照。
 * 対応形式: Markdown (.md), HTML (.html/.htm), テキスト (.txt)
 *
 * ORDER_057 / TASK_196: UIドキュメントツリービューとMarkdownビューアの実装
 * ORDER_095 / TASK_335: 複数ファイル形式対応（HTML/テキスト表示）
 * ORDER_103 / TASK_359: ドキュメント参照先のdev_workspace_path対応
 */

import React, { useState, useEffect, useCallback } from 'react';
import DOMPurify from 'dompurify';
import { MarkdownViewer } from './MarkdownViewer';
import type { DocFile, DocsListResult, DocContentResult } from '../preload';

interface DocsPanelProps {
  /** プロジェクトID */
  projectId: string;
}

/**
 * カテゴリ表示名マッピング
 */
const CATEGORY_LABELS: Record<string, string> = {
  root: 'ドキュメント',
  decisions: '技術的意思決定 (ADR)',
};

/**
 * ファイルアイコンコンポーネント
 */
const FileIcon: React.FC<{ fileId: string; className?: string }> = ({ fileId, className = 'w-4 h-4' }) => {
  // ファイルIDに応じたアイコンを返す
  const iconMap: Record<string, React.ReactNode> = {
    architecture: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
      </svg>
    ),
    db_schema: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
      </svg>
    ),
    api_spec: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
      </svg>
    ),
    dev_rules: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
      </svg>
    ),
    bug_history: (
      <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  };

  // デフォルトのドキュメントアイコン
  const defaultIcon = (
    <svg className={className} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
    </svg>
  );

  // ルートカテゴリのファイルIDで直接マッチ、サブカテゴリの場合はスラッシュ後の部分を使わずデフォルト
  const baseId = fileId.includes('/') ? fileId.split('/').pop() || fileId : fileId;
  return <>{iconMap[baseId] || defaultIcon}</>;
};

/**
 * ファイルサイズフォーマッタ
 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * DocsPanel コンポーネント
 *
 * 左右分割レイアウトでドキュメントツリーとMarkdownビューアを表示する。
 */
export const DocsPanel: React.FC<DocsPanelProps> = ({ projectId }) => {
  const [docsList, setDocsList] = useState<DocsListResult | null>(null);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [docContent, setDocContent] = useState<DocContentResult | null>(null);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [contentError, setContentError] = useState<string | null>(null);

  /**
   * docs一覧を取得
   */
  const loadDocsList = useCallback(async () => {
    if (!projectId) return;
    setIsLoadingList(true);
    setListError(null);
    setSelectedFileId(null);
    setDocContent(null);

    try {
      const result = await window.electronAPI.getDocsList(projectId);
      setDocsList(result);
      if (!result.success) {
        setListError(result.error || 'ドキュメント一覧の取得に失敗しました');
      }
    } catch (err) {
      console.error('[DocsPanel] Failed to load docs list:', err);
      setListError('ドキュメント一覧の取得中にエラーが発生しました');
    } finally {
      setIsLoadingList(false);
    }
  }, [projectId]);

  /**
   * ファイル内容を取得
   */
  const loadDocContent = useCallback(async (fileId: string) => {
    if (!projectId) return;
    setIsLoadingContent(true);
    setContentError(null);
    setSelectedFileId(fileId);

    try {
      const result = await window.electronAPI.getDocContent(projectId, fileId);
      setDocContent(result);
      if (!result.success) {
        setContentError(result.error || 'ドキュメントの読み込みに失敗しました');
      }
    } catch (err) {
      console.error('[DocsPanel] Failed to load doc content:', err);
      setContentError('ドキュメントの読み込み中にエラーが発生しました');
    } finally {
      setIsLoadingContent(false);
    }
  }, [projectId]);

  // プロジェクト変更時にdocs一覧を再取得
  useEffect(() => {
    loadDocsList();
  }, [loadDocsList]);

  /**
   * ファイルをカテゴリ別にグルーピング
   */
  const filesByCategory = React.useMemo(() => {
    if (!docsList?.files) return {};
    const grouped: Record<string, DocFile[]> = {};
    for (const file of docsList.files) {
      if (!grouped[file.category]) {
        grouped[file.category] = [];
      }
      grouped[file.category].push(file);
    }
    return grouped;
  }, [docsList]);

  const categories = React.useMemo(() => {
    if (!docsList?.categories) return [];
    return docsList.categories;
  }, [docsList]);

  // ローディング表示
  if (isLoadingList) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center text-gray-500">
          <svg className="animate-spin h-8 w-8 mb-3" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <span className="text-sm">ドキュメント一覧を読み込み中...</span>
        </div>
      </div>
    );
  }

  // エラー表示
  if (listError) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="flex items-start gap-3">
          <svg className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <div>
            <h3 className="text-sm font-medium text-gray-900">ドキュメントを取得できませんでした</h3>
            <p className="text-xs text-gray-500 mt-1">{listError}</p>
            <button
              onClick={loadDocsList}
              className="mt-3 text-xs text-blue-600 hover:text-blue-800 underline"
            >
              再読み込み
            </button>
          </div>
        </div>
      </div>
    );
  }

  // 空のドキュメント
  if (docsList?.success && (!docsList.files || docsList.files.length === 0)) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="text-center py-8">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-gray-100 rounded-full mb-4">
            <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 className="text-sm font-medium text-gray-900 mb-1">ドキュメントがありません</h3>
          <p className="text-xs text-gray-500">
            {docsList.message || 'docs/ディレクトリにファイルを追加してください（.md, .html, .txt）'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100vh-16rem)] bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
      {/* 左ペイン: ファイルツリー */}
      <div className="w-64 flex-shrink-0 border-r border-gray-200 flex flex-col">
        {/* ヘッダー */}
        <div className="px-3 py-2 border-b border-gray-100 flex items-center justify-between">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider" title={docsList?.docs_path || ''}>
            {docsList?.docs_source === 'dev_workspace' ? 'project/' : 'docs/'}
          </h3>
          <button
            onClick={loadDocsList}
            className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
            title="再読み込み"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>

        {/* ファイルツリー */}
        <div className="flex-1 overflow-y-auto py-1">
          {categories.map((category) => {
            const files = filesByCategory[category] || [];
            if (files.length === 0) return null;

            return (
              <div key={category} className="mb-1">
                {/* カテゴリがroot以外の場合はカテゴリヘッダーを表示 */}
                {category !== 'root' && (
                  <div className="px-3 py-1.5 flex items-center gap-1.5">
                    <svg className="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                    </svg>
                    <span className="text-xs font-medium text-gray-500">
                      {CATEGORY_LABELS[category] || `${category}/`}
                    </span>
                  </div>
                )}

                {/* ファイル一覧 */}
                {files.map((file) => {
                  const isSelected = selectedFileId === file.id;
                  return (
                    <button
                      key={file.id}
                      onClick={() => loadDocContent(file.id)}
                      className={`w-full text-left px-3 py-1.5 flex items-center gap-2 text-xs transition-colors ${
                        category !== 'root' ? 'pl-7' : ''
                      } ${
                        isSelected
                          ? 'bg-blue-50 text-blue-700 border-r-2 border-blue-500'
                          : 'text-gray-700 hover:bg-gray-50'
                      }`}
                      title={`${file.title} (${formatFileSize(file.size)})`}
                    >
                      <span className={`flex-shrink-0 ${isSelected ? 'text-blue-500' : 'text-gray-400'}`}>
                        <FileIcon fileId={file.id} className="w-3.5 h-3.5" />
                      </span>
                      <span className="truncate">{file.title}</span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>

        {/* フッター: ファイル数 + 参照元情報 */}
        {docsList?.files && (
          <div className="px-3 py-2 border-t border-gray-100 text-xs text-gray-400">
            <div>{docsList.files.length} ファイル</div>
            {docsList.fallback_used && (
              <div className="text-amber-500 mt-0.5" title="dev_workspace_pathが設定されていますがパスが見つからないため、docs/を参照しています">
                フォールバック中
              </div>
            )}
          </div>
        )}
      </div>

      {/* 右ペイン: Markdownビューア */}
      <div className="flex-1 overflow-y-auto">
        {/* コンテンツ読み込み中 */}
        {isLoadingContent && (
          <div className="flex items-center justify-center h-full">
            <div className="flex flex-col items-center text-gray-500">
              <svg className="animate-spin h-6 w-6 mb-2" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span className="text-xs">読み込み中...</span>
            </div>
          </div>
        )}

        {/* コンテンツエラー */}
        {!isLoadingContent && contentError && (
          <div className="p-6">
            <div className="flex items-start gap-2 text-red-600">
              <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <p className="text-sm font-medium">読み込みエラー</p>
                <p className="text-xs mt-1">{contentError}</p>
              </div>
            </div>
          </div>
        )}

        {/* コンテンツ表示 */}
        {!isLoadingContent && !contentError && docContent?.success && docContent.content && (
          <div className="p-6">
            {/* ファイル情報ヘッダー */}
            <div className="flex items-center gap-2 mb-4 pb-3 border-b border-gray-100">
              <span className="text-gray-400">
                <FileIcon fileId={docContent.file_id || ''} className="w-4 h-4" />
              </span>
              <span className="text-sm font-medium text-gray-900">{docContent.title}</span>
              {docContent.content_type && docContent.content_type !== 'markdown' && (
                <span className="text-xs text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                  {docContent.content_type === 'html' ? 'HTML' : 'TEXT'}
                </span>
              )}
              {docContent.relative_path && (
                <span className="text-xs text-gray-400 ml-auto">{docContent.relative_path}</span>
              )}
            </div>
            {/* content_typeに応じた表示切替 */}
            {(!docContent.content_type || docContent.content_type === 'markdown') && (
              <MarkdownViewer content={docContent.content} />
            )}
            {docContent.content_type === 'html' && (
              <div
                className="prose prose-sm max-w-none"
                dangerouslySetInnerHTML={{
                  __html: DOMPurify.sanitize(docContent.content, { USE_PROFILES: { html: true } })
                }}
              />
            )}
            {docContent.content_type === 'text' && (
              <pre className="text-sm text-gray-800 whitespace-pre-wrap break-words font-mono bg-gray-50 rounded-lg p-4 border border-gray-200 overflow-auto">
                {docContent.content}
              </pre>
            )}
          </div>
        )}

        {/* 未選択時のプレースホルダー */}
        {!isLoadingContent && !contentError && !docContent && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-12 h-12 bg-gray-100 rounded-full mb-3">
                <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <p className="text-sm text-gray-500">左のツリーからドキュメントを選択してください</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
