import React, { useState, useEffect, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import type { ArtifactFile, OrderReleaseInfo, OrderRelatedInfo } from '../preload';
import { ReleaseInfoCard } from './ReleaseInfoCard';
import { ReleaseDetailSection } from './ReleaseDetailSection';
import { RelatedInfoSection } from './RelatedInfoSection';

interface ArtifactsBrowserProps {
  /** プロジェクト名 */
  projectName: string;
  /** ORDER ID */
  orderId: string;
}

/**
 * 成果物ブラウザコンポーネント
 *
 * ORDER_XXXの成果物ファイル一覧を表示し、ファイル選択で内容を閲覧できる。
 * Markdownファイルはレンダリング表示、その他はファイルパス表示。
 *
 * TASK_194: ArtifactsBrowser実装
 * ORDER_045: ORDER成果物タブの情報充実化
 * TASK_601: リリース情報・関連情報セクション統合
 */
export const ArtifactsBrowser: React.FC<ArtifactsBrowserProps> = ({
  projectName,
  orderId,
}) => {
  const [files, setFiles] = useState<ArtifactFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<ArtifactFile | null>(null);
  const [fileContent, setFileContent] = useState<string | null>(null);
  const [contentLoading, setContentLoading] = useState(false);

  // ORDER_045: リリース情報・関連情報
  const [releaseInfo, setReleaseInfo] = useState<OrderReleaseInfo | null>(null);
  const [relatedInfo, setRelatedInfo] = useState<OrderRelatedInfo | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);

  // 成果物ファイル一覧を取得
  useEffect(() => {
    const fetchFiles = async () => {
      setLoading(true);
      setError(null);
      setSelectedFile(null);
      setFileContent(null);

      try {
        const artifactFiles = await window.electronAPI.getArtifactFiles(
          projectName,
          orderId
        );
        setFiles(artifactFiles);
      } catch (err) {
        console.error('[ArtifactsBrowser] Failed to fetch artifact files:', err);
        setError('成果物ファイル一覧の取得に失敗しました');
      } finally {
        setLoading(false);
      }
    };

    fetchFiles();
  }, [projectName, orderId]);

  // ORDER_045: リリース情報・関連情報を取得
  useEffect(() => {
    const fetchMetaInfo = async () => {
      setMetaLoading(true);

      try {
        const [releaseResult, relatedResult] = await Promise.all([
          window.electronAPI.getOrderReleaseInfo(projectName, orderId),
          window.electronAPI.getOrderRelatedInfo(projectName, orderId),
        ]);
        setReleaseInfo(releaseResult);
        setRelatedInfo(relatedResult);
      } catch (err) {
        console.error('[ArtifactsBrowser] Failed to fetch meta info:', err);
        // エラーでもUIは表示する（グレースフルデグラデーション）
        setReleaseInfo({ hasRelease: false, releases: [] });
        setRelatedInfo({ relatedBacklogs: [], dependentOrders: [] });
      } finally {
        setMetaLoading(false);
      }
    };

    fetchMetaInfo();
  }, [projectName, orderId]);

  // ファイル選択時に内容を取得
  useEffect(() => {
    if (!selectedFile || selectedFile.type === 'directory') {
      setFileContent(null);
      return;
    }

    const fetchContent = async () => {
      setContentLoading(true);

      try {
        const content = await window.electronAPI.getArtifactContent(
          projectName,
          orderId,
          selectedFile.path
        );
        setFileContent(content);
      } catch (err) {
        console.error('[ArtifactsBrowser] Failed to fetch file content:', err);
        setFileContent(null);
      } finally {
        setContentLoading(false);
      }
    };

    fetchContent();
  }, [projectName, orderId, selectedFile]);

  // ファイルのみをフィルタ（ディレクトリは除外）
  const fileList = useMemo(
    () => files.filter((f) => f.type === 'file'),
    [files]
  );

  // 関連バックログIDを抽出
  const relatedBacklogIds = useMemo(
    () => relatedInfo?.relatedBacklogs.map((b) => b.id) ?? [],
    [relatedInfo]
  );

  // ファイルアイコンを取得
  const getFileIcon = (file: ArtifactFile) => {
    if (file.type === 'directory') {
      return (
        <svg className="w-4 h-4 text-yellow-500" fill="currentColor" viewBox="0 0 20 20">
          <path d="M2 6a2 2 0 012-2h5l2 2h5a2 2 0 012 2v6a2 2 0 01-2 2H4a2 2 0 01-2-2V6z" />
        </svg>
      );
    }

    // Markdownファイル
    if (file.extension === '.md') {
      return (
        <svg className="w-4 h-4 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      );
    }

    // TypeScript/JavaScript
    if (file.extension === '.ts' || file.extension === '.tsx' || file.extension === '.js' || file.extension === '.jsx') {
      return (
        <svg className="w-4 h-4 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
      );
    }

    // Python
    if (file.extension === '.py') {
      return (
        <svg className="w-4 h-4 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
        </svg>
      );
    }

    // その他のファイル
    return (
      <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
      </svg>
    );
  };

  // Markdownファイルかどうか判定
  const isMarkdown = (file: ArtifactFile | null): boolean => {
    return file?.extension === '.md';
  };

  // 初期ローディング表示
  if (loading && metaLoading) {
    return (
      <div className="flex items-center justify-center h-32">
        <svg
          className="animate-spin h-6 w-6 text-blue-500"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
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
        <span className="ml-2 text-sm text-gray-500">読み込み中...</span>
      </div>
    );
  }

  // エラー表示
  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-32 text-center">
        <svg
          className="w-8 h-8 text-gray-400 mb-2"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
        <p className="text-sm text-gray-500">{error}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* ORDER_045: リリース情報・関連情報セクション */}
      <div className="flex-shrink-0 p-4 border-b border-gray-200 overflow-auto max-h-80">
        {metaLoading ? (
          <div className="flex items-center justify-center h-16">
            <svg
              className="animate-spin h-5 w-5 text-blue-500"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
            <span className="ml-2 text-sm text-gray-500">メタ情報を読み込み中...</span>
          </div>
        ) : (
          <>
            {/* リリースサマリカード */}
            {releaseInfo && (
              <ReleaseInfoCard
                releaseInfo={releaseInfo}
                relatedBacklogIds={relatedBacklogIds}
              />
            )}

            {/* リリース詳細セクション */}
            {releaseInfo && releaseInfo.hasRelease && (
              <ReleaseDetailSection releases={releaseInfo.releases} />
            )}

            {/* 関連情報セクション */}
            {relatedInfo && (
              <RelatedInfoSection relatedInfo={relatedInfo} />
            )}
          </>
        )}
      </div>

      {/* ファイル一覧・内容表示 */}
      <div className="flex flex-1 min-h-0">
        {/* ファイル一覧パネル */}
        <div className="w-1/3 border-r border-gray-200 overflow-auto">
          <div className="p-2">
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 px-2">
              成果物ファイル ({fileList.length})
            </h4>
            {fileList.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-24 text-center">
                <svg
                  className="w-8 h-8 text-gray-300 mb-1"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4"
                  />
                </svg>
                <p className="text-xs text-gray-400">ファイルなし</p>
              </div>
            ) : (
              <ul className="space-y-0.5">
                {fileList.map((file) => (
                  <li key={file.path}>
                    <button
                      onClick={() => setSelectedFile(file)}
                      className={`w-full flex items-center px-2 py-1.5 text-left text-sm rounded-md transition-colors ${
                        selectedFile?.path === file.path
                          ? 'bg-blue-100 text-blue-700'
                          : 'text-gray-700 hover:bg-gray-100'
                      }`}
                      title={file.path}
                    >
                      <span className="flex-shrink-0 mr-2">{getFileIcon(file)}</span>
                      <span className="truncate">{file.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* コンテンツ表示パネル */}
        <div className="flex-1 overflow-auto p-4">
          {!selectedFile && (
            <div className="flex flex-col items-center justify-center h-full text-center">
              <svg
                className="w-12 h-12 text-gray-300 mb-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                />
              </svg>
              <p className="text-sm text-gray-500">ファイルを選択してください</p>
            </div>
          )}

          {selectedFile && contentLoading && (
            <div className="flex items-center justify-center h-32">
              <svg
                className="animate-spin h-5 w-5 text-blue-500"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
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
              <span className="ml-2 text-sm text-gray-500">読み込み中...</span>
            </div>
          )}

          {selectedFile && !contentLoading && fileContent === null && (
            <div className="text-center py-8">
              <p className="text-sm text-gray-500">
                ファイル内容を取得できませんでした
              </p>
              <p className="text-xs text-gray-400 mt-1">{selectedFile.path}</p>
            </div>
          )}

          {selectedFile && !contentLoading && fileContent !== null && (
            <div>
              {/* ファイルパスヘッダー */}
              <div className="flex items-center mb-3 pb-2 border-b border-gray-200">
                <span className="flex-shrink-0 mr-2">{getFileIcon(selectedFile)}</span>
                <span className="text-sm font-medium text-gray-700 truncate">
                  {selectedFile.path}
                </span>
              </div>

              {/* Markdownレンダリング */}
              {isMarkdown(selectedFile) ? (
                <div className="prose prose-sm max-w-none">
                  <ReactMarkdown
                    components={{
                      h1: ({ children }) => (
                        <h1 className="text-xl font-bold text-gray-900 mt-4 mb-2 first:mt-0">
                          {children}
                        </h1>
                      ),
                      h2: ({ children }) => (
                        <h2 className="text-lg font-semibold text-gray-800 mt-4 mb-2 border-b border-gray-200 pb-1">
                          {children}
                        </h2>
                      ),
                      h3: ({ children }) => (
                        <h3 className="text-base font-semibold text-gray-700 mt-3 mb-1">
                          {children}
                        </h3>
                      ),
                      p: ({ children }) => (
                        <p className="text-sm text-gray-600 my-2">{children}</p>
                      ),
                      ul: ({ children }) => (
                        <ul className="list-disc list-inside text-sm text-gray-600 my-2 space-y-1">
                          {children}
                        </ul>
                      ),
                      ol: ({ children }) => (
                        <ol className="list-decimal list-inside text-sm text-gray-600 my-2 space-y-1">
                          {children}
                        </ol>
                      ),
                      li: ({ children }) => (
                        <li className="text-sm text-gray-600">{children}</li>
                      ),
                      code: ({ children, className }) => {
                        const isInline = !className;
                        return isInline ? (
                          <code className="bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-xs font-mono">
                            {children}
                          </code>
                        ) : (
                          <code className="block bg-gray-50 text-gray-800 p-3 rounded-md text-xs font-mono overflow-x-auto">
                            {children}
                          </code>
                        );
                      },
                      pre: ({ children }) => (
                        <pre className="bg-gray-50 p-3 rounded-md overflow-x-auto my-2">
                          {children}
                        </pre>
                      ),
                      table: ({ children }) => (
                        <div className="overflow-x-auto my-2">
                          <table className="min-w-full text-sm border-collapse border border-gray-200">
                            {children}
                          </table>
                        </div>
                      ),
                      th: ({ children }) => (
                        <th className="border border-gray-200 bg-gray-50 px-3 py-1.5 text-left font-medium text-gray-700">
                          {children}
                        </th>
                      ),
                      td: ({ children }) => (
                        <td className="border border-gray-200 px-3 py-1.5 text-gray-600">
                          {children}
                        </td>
                      ),
                      blockquote: ({ children }) => (
                        <blockquote className="border-l-4 border-gray-300 pl-3 my-2 text-sm text-gray-600 italic">
                          {children}
                        </blockquote>
                      ),
                      a: ({ href, children }) => (
                        <a
                          href={href}
                          className="text-blue-600 hover:underline"
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {children}
                        </a>
                      ),
                      hr: () => <hr className="my-4 border-gray-200" />,
                    }}
                  >
                    {fileContent}
                  </ReactMarkdown>
                </div>
              ) : (
                /* プレーンテキスト表示 */
                <pre className="bg-gray-50 p-4 rounded-md text-xs font-mono text-gray-700 overflow-x-auto whitespace-pre-wrap">
                  {fileContent}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
