import React, { useState, useEffect, useCallback } from 'react';
import { resolveArtifactsDirPath } from '../utils/artifactPaths';

interface OrderCompleteReportProps {
  /** プロジェクトID */
  projectId: string;
  /** ORDER ID */
  orderId: string;
  /** ORDER タイトル */
  orderTitle?: string;
}

/**
 * レポートMarkdownからartifactsフィールドを抽出する
 */
function parseArtifactsFromReport(reportContent: string): string[] {
  const jsonMatch = reportContent.match(/```json\s*([\s\S]*?)```/);
  if (!jsonMatch) return [];
  try {
    const data = JSON.parse(jsonMatch[1]);
    if (Array.isArray(data.artifacts)) {
      return data.artifacts.filter((a: unknown) => typeof a === 'string');
    }
  } catch {
    // JSONパース失敗は無視
  }
  return [];
}

/**
 * ORDER完了レポート表示コンポーネント
 *
 * ORDER完了時のサマリー情報と、成果物フォルダを開くボタン・
 * 個別ファイルのダウンロードボタンを提供する。
 *
 * ORDER_053 / TASK_181: ORDER完了レポート画面に成果物フォルダを開くボタンを追加
 * ORDER_086 / TASK_298: 成果物ファイル一覧とダウンロード機能を追加
 */
export const OrderCompleteReport: React.FC<OrderCompleteReportProps> = ({
  projectId,
  orderId,
  orderTitle,
}) => {
  const [folderError, setFolderError] = useState<string | null>(null);
  const [isOpening, setIsOpening] = useState(false);
  const [artifacts, setArtifacts] = useState<string[]>([]);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  // ORDER内の全タスクレポートから成果物を収集
  useEffect(() => {
    let cancelled = false;

    const loadArtifacts = async () => {
      try {
        const reportList = await window.electronAPI.getOrderReportList(projectId, orderId);
        const allArtifacts: string[] = [];

        await Promise.all(
          reportList.map(async (reportFilename) => {
            try {
              const reportFile = await window.electronAPI.getOrderReport(projectId, orderId, reportFilename);
              if (reportFile?.content) {
                const found = parseArtifactsFromReport(reportFile.content);
                allArtifacts.push(...found);
              }
            } catch {
              // 個別レポート読み込み失敗は無視
            }
          })
        );

        // 重複除去
        const unique = Array.from(new Set(allArtifacts));
        if (!cancelled) {
          setArtifacts(unique);
        }
      } catch {
        // レポート一覧取得失敗は無視（成果物セクションを空で表示）
      }
    };

    loadArtifacts();

    return () => {
      cancelled = true;
    };
  }, [projectId, orderId]);

  const handleOpenArtifactsFolder = async () => {
    setFolderError(null);
    setIsOpening(true);

    try {
      const dirPath = await resolveArtifactsDirPath(projectId, orderId);
      const result = await window.electronAPI.openArtifactsFolder(dirPath);

      if (!result.success) {
        setFolderError(
          result.error ||
            '成果物フォルダを開けませんでした。フォルダが存在しない可能性があります。'
        );
      }
    } catch (err) {
      console.error('[OrderCompleteReport] Failed to open artifacts folder:', err);
      setFolderError('成果物フォルダを開く際にエラーが発生しました。');
    } finally {
      setIsOpening(false);
    }
  };

  const handleDownloadArtifactFile = useCallback(async (absoluteFilePath: string) => {
    setArtifactError(null);
    try {
      const fileName = absoluteFilePath.replace(/\\/g, '/').split('/').pop() || 'file';
      const result = await window.electronAPI.downloadArtifactFile(absoluteFilePath, fileName);
      if (!result.success && !result.canceled) {
        setArtifactError(result.error || 'ダウンロードに失敗しました');
      }
    } catch {
      setArtifactError('ダウンロード処理でエラーが発生しました');
    }
  }, []);

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      {/* ヘッダー */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <svg
            className="w-5 h-5 text-green-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <h3 className="text-base font-semibold text-gray-800">
            {orderId} 完了レポート
          </h3>
          {orderTitle && (
            <span className="text-sm text-gray-500">: {orderTitle}</span>
          )}
        </div>

        {/* 成果物フォルダを開くボタン */}
        <button
          onClick={handleOpenArtifactsFolder}
          disabled={isOpening}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 disabled:cursor-not-allowed rounded-md transition-colors duration-150"
          title="成果物フォルダをファイルマネージャーで開く"
        >
          {isOpening ? (
            <svg
              className="w-4 h-4 animate-spin"
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
          ) : (
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z"
              />
            </svg>
          )}
          成果物フォルダを開く
        </button>
      </div>

      {/* フォルダエラーメッセージ */}
      {folderError && (
        <div className="flex items-start gap-2 mt-2 p-3 bg-red-50 border border-red-200 rounded-md">
          <svg
            className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
            />
          </svg>
          <p className="text-sm text-red-700">{folderError}</p>
        </div>
      )}

      {/* 成果物ファイル一覧 */}
      <div className="mt-3">
        <h4 className="text-sm font-semibold text-gray-500 uppercase mb-2">
          成果物ファイル {artifacts.length > 0 ? `(${artifacts.length})` : ''}
        </h4>

        {/* ダウンロードエラーメッセージ */}
        {artifactError && (
          <p className="text-xs text-red-600 bg-red-50 px-3 py-1.5 rounded border border-red-200 mb-2">
            {artifactError}
          </p>
        )}

        {artifacts.length > 0 ? (
          <div className="space-y-1">
            {artifacts.map((filePath, idx) => {
              const fileName = filePath.replace(/\\/g, '/').split('/').pop() || filePath;
              return (
                <div
                  key={idx}
                  className="flex items-center justify-between gap-2 px-3 py-2 bg-gray-50 rounded border border-gray-200"
                >
                  <span className="text-sm text-gray-700 truncate" title={filePath}>
                    {fileName}
                  </span>
                  <button
                    onClick={() => handleDownloadArtifactFile(filePath)}
                    className="flex-shrink-0 flex items-center gap-1 px-2 py-1 bg-green-50 text-green-700 border border-green-200 rounded hover:bg-green-100 transition text-xs font-medium"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    ダウンロード
                  </button>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-gray-400 italic">成果物なし</p>
        )}
      </div>
    </div>
  );
};
