/**
 * ProjectPageGenerator Component
 *
 * プロジェクト紹介ページ生成・プレビュー・エクスポートコンポーネント
 * ORDER_021 / TASK_068
 */

import React, { useState, useCallback, useRef } from 'react';

interface ProjectPageGeneratorProps {
  projectId: string;
}

type GenerateState = 'idle' | 'generating' | 'done' | 'error';

export const ProjectPageGenerator: React.FC<ProjectPageGeneratorProps> = ({ projectId }) => {
  const [state, setState] = useState<GenerateState>('idle');
  const [html, setHtml] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [exportResult, setExportResult] = useState<{ success: boolean; filePath?: string; canceled?: boolean } | null>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const handleGenerate = useCallback(async () => {
    setState('generating');
    setHtml(null);
    setErrorMsg(null);
    setExportResult(null);

    try {
      const result = await window.electronAPI.generateProjectPage(projectId);
      if (result.success && result.html) {
        setHtml(result.html);
        setState('done');
      } else {
        setErrorMsg(result.error ?? '生成に失敗しました');
        setState('error');
      }
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : '生成中にエラーが発生しました');
      setState('error');
    }
  }, [projectId]);

  const handleExport = useCallback(async () => {
    setIsExporting(true);
    setExportResult(null);

    try {
      const result = await window.electronAPI.exportProjectPage(projectId);
      setExportResult(result);
    } catch (err) {
      setExportResult({ success: false });
    } finally {
      setIsExporting(false);
    }
  }, [projectId]);

  return (
    <div className="bg-white rounded-lg shadow p-4 space-y-4">
      {/* ヘッダー */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <svg className="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <h3 className="text-sm font-semibold text-gray-800">紹介ページ生成</h3>
        </div>

        <div className="flex items-center gap-2">
          {/* 生成ボタン */}
          <button
            onClick={handleGenerate}
            disabled={state === 'generating'}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {state === 'generating' ? (
              <>
                <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                生成中...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                {state === 'done' ? '再生成' : '紹介ページ生成'}
              </>
            )}
          </button>

          {/* エクスポートボタン（生成後のみ表示） */}
          {state === 'done' && (
            <button
              onClick={handleExport}
              disabled={isExporting}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md bg-green-600 text-white hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isExporting ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  保存中...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  HTMLをエクスポート
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* エクスポート結果メッセージ */}
      {exportResult && (
        <div className={`text-sm px-3 py-2 rounded-md ${exportResult.canceled ? 'bg-gray-100 text-gray-600' : exportResult.success ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          {exportResult.canceled
            ? 'エクスポートをキャンセルしました'
            : exportResult.success
              ? `保存しました: ${exportResult.filePath ?? ''}`
              : 'エクスポートに失敗しました'}
        </div>
      )}

      {/* エラーメッセージ */}
      {state === 'error' && errorMsg && (
        <div className="text-sm px-3 py-2 rounded-md bg-red-50 text-red-700 border border-red-200">
          {errorMsg}
        </div>
      )}

      {/* プレビュー（iframe） */}
      {state === 'done' && html && (
        <div className="border border-gray-200 rounded-md overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-50 border-b border-gray-200">
            <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
            </svg>
            <span className="text-xs text-gray-500 font-medium">プレビュー</span>
          </div>
          <iframe
            ref={iframeRef}
            srcDoc={html}
            title="プロジェクト紹介ページ プレビュー"
            className="w-full"
            style={{ height: '600px', border: 'none' }}
            sandbox="allow-same-origin"
          />
        </div>
      )}

      {/* アイドル状態のヒント */}
      {state === 'idle' && (
        <div className="text-xs text-gray-400 text-center py-4">
          「紹介ページ生成」ボタンをクリックして、プロジェクトの紹介ページを生成します
        </div>
      )}
    </div>
  );
};
