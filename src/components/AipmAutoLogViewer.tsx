/**
 * AipmAutoLogViewer Component
 *
 * aipm_auto (Python自動実行スクリプト) の実行ログを表示するコンポーネント
 *
 * ORDER_050: aipm_autoの実行ログをダッシュボードから確認可能にする
 * TASK_619: AipmAutoLogViewerコンポーネント実装
 *
 * 機能:
 * - プロジェクト選択
 * - ログファイル一覧表示
 * - ログ内容のリアルタイム表示
 * - フォロー機能（tail -f相当）
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import type {
  LogFileInfo,
  LogContent,
  LogUpdateEvent,
  LogDirectoryInfo,
} from '../preload';

// =============================================================================
// 型定義
// =============================================================================

interface AipmAutoLogViewerProps {
  /** 初期表示行数（デフォルト: 100） */
  initialTailLines?: number;
  /** プロジェクト名（指定時は選択を非表示） */
  projectName?: string;
}

// =============================================================================
// 定数
// =============================================================================

/** ログレベルに対応する色クラス */
const LOG_LEVEL_COLORS: Record<string, string> = {
  '[DEBUG]': 'text-gray-400',
  '[INFO]': 'text-blue-400',
  '[OK]': 'text-green-400',
  '[WARN]': 'text-yellow-400',
  '[ERROR]': 'text-red-400',
};

// =============================================================================
// メインコンポーネント
// =============================================================================

export const AipmAutoLogViewer: React.FC<AipmAutoLogViewerProps> = ({
  initialTailLines = 100,
  projectName: initialProject,
}) => {
  // 状態管理
  const [directories, setDirectories] = useState<LogDirectoryInfo[]>([]);
  const [selectedProject, setSelectedProject] = useState<string>(initialProject || '');
  const [logFiles, setLogFiles] = useState<LogFileInfo[]>([]);
  const [selectedFile, setSelectedFile] = useState<LogFileInfo | null>(null);
  const [logContent, setLogContent] = useState<LogContent | null>(null);
  const [isFollowing, setIsFollowing] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [isWatching, setIsWatching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ref
  const logContainerRef = useRef<HTMLPreElement>(null);
  const lastReadPositionRef = useRef<number>(0);

  // ディレクトリ一覧取得
  const fetchDirectories = useCallback(async () => {
    try {
      const dirs = await window.electronAPI.getAipmAutoLogDirectories();
      setDirectories(dirs);
      if (!selectedProject && dirs.length > 0) {
        setSelectedProject(dirs[0].projectName);
      }
    } catch (err) {
      console.error('[AipmAutoLogViewer] Failed to fetch directories:', err);
      setError('ログディレクトリの取得に失敗しました');
    }
  }, [selectedProject]);

  // ログファイル一覧取得
  const fetchLogFiles = useCallback(async (project: string) => {
    if (!project) return;
    try {
      setIsLoading(true);
      const files = await window.electronAPI.getAipmAutoLogFiles(project);
      setLogFiles(files);
      // 最新のファイルを自動選択
      if (files.length > 0 && (!selectedFile || selectedFile.projectName !== project)) {
        setSelectedFile(files[0]);
      }
    } catch (err) {
      console.error('[AipmAutoLogViewer] Failed to fetch log files:', err);
      setError('ログファイル一覧の取得に失敗しました');
    } finally {
      setIsLoading(false);
    }
  }, [selectedFile]);

  // ログ内容取得
  const fetchLogContent = useCallback(async (file: LogFileInfo, tailLines?: number) => {
    if (!file) return;
    try {
      const content = await window.electronAPI.readAipmAutoLogFile(
        file.filePath,
        tailLines ? { tailLines } : undefined
      );
      if (content) {
        setLogContent(content);
        lastReadPositionRef.current = content.readPosition;
        setError(null);
      }
    } catch (err) {
      console.error('[AipmAutoLogViewer] Failed to read log file:', err);
      setError('ログファイルの読み込みに失敗しました');
    }
  }, []);

  // 差分取得
  const fetchDiff = useCallback(async () => {
    if (!selectedFile) return;
    try {
      const content = await window.electronAPI.readAipmAutoLogFile(
        selectedFile.filePath,
        { fromPosition: lastReadPositionRef.current }
      );
      if (content && content.content) {
        setLogContent((prev) => {
          if (!prev) return content;
          return {
            ...prev,
            content: prev.content + content.content,
            totalLines: prev.totalLines + content.lineCount,
            fileSize: content.fileSize,
            readPosition: content.readPosition,
          };
        });
        lastReadPositionRef.current = content.readPosition;
      }
    } catch (err) {
      console.error('[AipmAutoLogViewer] Failed to fetch diff:', err);
    }
  }, [selectedFile]);

  // 監視開始
  const startWatching = useCallback(async (project: string) => {
    try {
      const result = await window.electronAPI.startAipmAutoLogWatcher(project);
      if (result.success) {
        setIsWatching(true);
      } else {
        console.warn('[AipmAutoLogViewer] Failed to start watcher:', result.error);
      }
    } catch (err) {
      console.error('[AipmAutoLogViewer] Failed to start watcher:', err);
    }
  }, []);

  // 監視停止
  const stopWatching = useCallback(async () => {
    try {
      await window.electronAPI.stopAipmAutoLogWatcher();
      setIsWatching(false);
    } catch (err) {
      console.error('[AipmAutoLogViewer] Failed to stop watcher:', err);
    }
  }, []);

  // 自動スクロール
  const scrollToBottom = useCallback(() => {
    if (logContainerRef.current && isFollowing) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [isFollowing]);

  // 初回読み込み
  useEffect(() => {
    fetchDirectories();
  }, [fetchDirectories]);

  // プロジェクト変更時
  useEffect(() => {
    if (selectedProject) {
      fetchLogFiles(selectedProject);
      startWatching(selectedProject);
    }
    return () => {
      stopWatching();
    };
  }, [selectedProject, fetchLogFiles, startWatching, stopWatching]);

  // ファイル選択時
  useEffect(() => {
    if (selectedFile) {
      fetchLogContent(selectedFile, initialTailLines);
    }
  }, [selectedFile, fetchLogContent, initialTailLines]);

  // ログ更新時のスクロール
  useEffect(() => {
    scrollToBottom();
  }, [logContent, scrollToBottom]);

  // ログ更新イベントリスナー
  useEffect(() => {
    const unsubscribe = window.electronAPI.onAipmAutoLogUpdate((event: LogUpdateEvent) => {
      if (event.type === 'change' && selectedFile && event.filePath === selectedFile.filePath) {
        // 差分を追加
        if (event.appendedContent) {
          setLogContent((prev) => {
            if (!prev) return prev;
            return {
              ...prev,
              content: prev.content + event.appendedContent,
              totalLines: prev.totalLines + (event.appendedContent?.split('\n').length || 0),
              fileSize: event.newSize || prev.fileSize,
            };
          });
        } else {
          // 差分取得
          fetchDiff();
        }
      } else if (event.type === 'add') {
        // 新しいファイルが追加された場合、一覧を更新
        fetchLogFiles(selectedProject);
      }
    });
    return () => unsubscribe();
  }, [selectedFile, selectedProject, fetchDiff, fetchLogFiles]);

  // プロジェクト変更ハンドラ
  const handleProjectChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedProject(e.target.value);
    setSelectedFile(null);
    setLogContent(null);
  }, []);

  // ファイル変更ハンドラ
  const handleFileChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    const filePath = e.target.value;
    const file = logFiles.find((f) => f.filePath === filePath);
    if (file) {
      setSelectedFile(file);
      lastReadPositionRef.current = 0;
    }
  }, [logFiles]);

  // フォロー切り替えハンドラ
  const handleToggleFollow = useCallback(() => {
    setIsFollowing((prev) => !prev);
  }, []);

  // リフレッシュハンドラ
  const handleRefresh = useCallback(async () => {
    if (selectedFile) {
      lastReadPositionRef.current = 0;
      await fetchLogContent(selectedFile, initialTailLines);
    }
  }, [selectedFile, fetchLogContent, initialTailLines]);

  // ローディング表示
  if (isLoading && !logContent) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-8">
        <div className="flex items-center justify-center">
          <svg
            className="animate-spin h-6 w-6 text-blue-500"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span className="ml-2 text-sm text-gray-500">ログを読み込み中...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm flex flex-col h-full">
      {/* ヘッダー */}
      <div className="flex items-center justify-between p-4 border-b border-gray-100 flex-shrink-0">
        <div className="flex items-center gap-4">
          <h3 className="font-medium text-gray-800">aipm_auto ログ</h3>

          {/* プロジェクト選択 */}
          {!initialProject && (
            <select
              value={selectedProject}
              onChange={handleProjectChange}
              className="text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">プロジェクトを選択</option>
              {directories.map((dir) => (
                <option key={dir.projectName} value={dir.projectName}>
                  {dir.projectName}{dir.fileCount !== undefined ? ` (${dir.fileCount}件)` : ''}
                </option>
              ))}
            </select>
          )}

          {/* ファイル選択 */}
          {logFiles.length > 0 && (
            <select
              value={selectedFile?.filePath || ''}
              onChange={handleFileChange}
              className="text-sm border border-gray-300 rounded-md px-2 py-1 focus:outline-none focus:ring-2 focus:ring-blue-500 max-w-xs"
            >
              {logFiles.map((file) => (
                <option key={file.filePath} value={file.filePath}>
                  {file.fileName} ({formatFileSize(file.size)})
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* 監視状態 */}
          {isWatching && (
            <span className="flex items-center gap-1 text-xs text-green-600">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
              監視中
            </span>
          )}

          {/* フォロートグル */}
          <button
            onClick={handleToggleFollow}
            className={`flex items-center gap-1 px-2 py-1 text-xs rounded-md transition-colors ${
              isFollowing
                ? 'bg-blue-100 text-blue-700'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}
            title={isFollowing ? 'フォロー中（自動スクロール）' : 'フォロー停止'}
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 14l-7 7m0 0l-7-7m7 7V3" />
            </svg>
            Follow
          </button>

          {/* リフレッシュボタン */}
          <button
            onClick={handleRefresh}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
            title="更新"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* エラー表示 */}
      {error && (
        <div className="p-4 bg-red-50 border-b border-red-200">
          <div className="flex items-center gap-2 text-sm text-red-700">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            {error}
          </div>
        </div>
      )}

      {/* ログ内容 */}
      <div className="flex-1 overflow-hidden">
        {!selectedProject ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <p className="text-sm text-gray-500">プロジェクトを選択してください</p>
          </div>
        ) : logFiles.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center p-8">
            <div className="w-12 h-12 bg-gray-100 rounded-full flex items-center justify-center mb-4">
              <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </div>
            <p className="text-sm text-gray-500 mb-1">ログファイルがありません</p>
            <p className="text-xs text-gray-400">
              aipm_auto を実行すると、ここにログが表示されます
            </p>
          </div>
        ) : (
          <pre
            ref={logContainerRef}
            className="h-full overflow-auto bg-gray-900 text-gray-100 text-xs p-4 font-mono whitespace-pre-wrap"
            onScroll={(e) => {
              const target = e.currentTarget;
              const isAtBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + 50;
              if (!isAtBottom && isFollowing) {
                setIsFollowing(false);
              }
            }}
          >
            {logContent?.content ? (
              <LogContentRenderer content={logContent.content} />
            ) : (
              <span className="text-gray-500">ログを読み込み中...</span>
            )}
          </pre>
        )}
      </div>

      {/* フッター */}
      {logContent && (
        <div className="flex items-center justify-between px-4 py-2 border-t border-gray-200 bg-gray-50 text-xs text-gray-500 flex-shrink-0">
          <span>
            {logContent.totalLines} 行
            {logContent.startLine > 0 && ` (${logContent.startLine + 1}行目から表示)`}
          </span>
          <span>{formatFileSize(logContent.fileSize)}</span>
        </div>
      )}
    </div>
  );
};

// =============================================================================
// サブコンポーネント
// =============================================================================

interface LogContentRendererProps {
  content: string;
}

/**
 * ログ内容をシンタックスハイライト付きでレンダリング
 */
const LogContentRenderer: React.FC<LogContentRendererProps> = ({ content }) => {
  const lines = content.split('\n');

  return (
    <>
      {lines.map((line, index) => (
        <LogLine key={index} line={line} />
      ))}
    </>
  );
};

interface LogLineProps {
  line: string;
}

const LogLine: React.FC<LogLineProps> = React.memo(({ line }) => {
  // ログレベルを検出
  let colorClass = 'text-gray-100';
  for (const [level, color] of Object.entries(LOG_LEVEL_COLORS)) {
    if (line.includes(level)) {
      colorClass = color;
      break;
    }
  }

  // 区切り線を検出
  if (line.includes('=====') || line.includes('-----')) {
    colorClass = 'text-gray-500';
  }

  return <div className={colorClass}>{line || ' '}</div>;
});

LogLine.displayName = 'LogLine';

// =============================================================================
// ユーティリティ関数
// =============================================================================

/**
 * ファイルサイズをフォーマット
 */
function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// =============================================================================
// エクスポート
// =============================================================================

export default AipmAutoLogViewer;
