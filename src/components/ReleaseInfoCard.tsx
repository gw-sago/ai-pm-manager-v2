import React from 'react';
import type { OrderReleaseInfo } from '../preload';

interface ReleaseInfoCardProps {
  /** リリース情報 */
  releaseInfo: OrderReleaseInfo;
  /** 関連バックログID一覧 */
  relatedBacklogIds?: string[];
}

/**
 * リリースサマリカードコンポーネント
 *
 * ORDER_045: ORDER成果物タブの情報充実化
 * TASK_598: ReleaseInfoCard実装
 *
 * リリース情報のサマリを表示するカードコンポーネント。
 * バージョン、日時、ファイル数、関連バックログを表示する。
 */
export const ReleaseInfoCard: React.FC<ReleaseInfoCardProps> = ({
  releaseInfo,
  relatedBacklogIds = [],
}) => {
  // リリースがない場合
  if (!releaseInfo.hasRelease) {
    return (
      <div className="bg-gray-50 border border-gray-200 rounded-lg p-4 mb-4">
        <div className="flex items-center">
          <svg
            className="w-5 h-5 text-gray-400 mr-2"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span className="text-sm text-gray-500">未リリース</span>
        </div>
        {relatedBacklogIds.length > 0 && (
          <div className="mt-3 pt-3 border-t border-gray-200">
            <span className="text-xs text-gray-400">関連バックログ: </span>
            {relatedBacklogIds.map((id) => (
              <span
                key={id}
                className="inline-block bg-gray-100 text-gray-600 text-xs px-2 py-0.5 rounded ml-1"
              >
                {id}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  // 最新リリース
  const latestRelease = releaseInfo.releases[0];
  const totalFileCount = releaseInfo.releases.reduce(
    (sum, r) => sum + r.fileCount,
    0
  );

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4 mb-4 shadow-sm">
      <div className="flex items-start justify-between">
        {/* バージョン情報 */}
        <div className="flex items-center">
          <div className="flex items-center justify-center w-10 h-10 bg-green-100 rounded-full mr-3">
            <svg
              className="w-5 h-5 text-green-600"
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
          </div>
          <div>
            <div className="flex items-center">
              {releaseInfo.latestVersion ? (
                <span className="text-lg font-bold text-gray-900">
                  {releaseInfo.latestVersion}
                </span>
              ) : (
                <span className="text-lg font-medium text-gray-700">
                  リリース済み
                </span>
              )}
              <span className="ml-2 px-2 py-0.5 bg-green-100 text-green-800 text-xs rounded-full">
                {releaseInfo.releases.length}回リリース
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              最終: {latestRelease.date}
            </p>
          </div>
        </div>

        {/* 統計情報 */}
        <div className="text-right">
          <div className="text-2xl font-semibold text-gray-700">
            {totalFileCount}
          </div>
          <div className="text-xs text-gray-500">ファイル</div>
        </div>
      </div>

      {/* 最新リリースの概要 */}
      {latestRelease.summary && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <p className="text-sm text-gray-600">{latestRelease.summary}</p>
        </div>
      )}

      {/* 関連バックログ */}
      {relatedBacklogIds.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-100">
          <span className="text-xs text-gray-400">関連バックログ: </span>
          {relatedBacklogIds.map((id) => (
            <span
              key={id}
              className="inline-block bg-blue-50 text-blue-700 text-xs px-2 py-0.5 rounded ml-1"
            >
              {id}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
