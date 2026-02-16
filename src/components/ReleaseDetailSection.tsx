import React, { useState } from 'react';
import type { ReleaseInfo } from '../preload';

interface ReleaseDetailSectionProps {
  /** リリース情報一覧 */
  releases: ReleaseInfo[];
}

/**
 * リリース詳細セクションコンポーネント
 *
 * ORDER_045: ORDER成果物タブの情報充実化
 * TASK_599: ReleaseDetailSection実装
 *
 * リリース詳細（ファイル一覧、変更内容）を折りたたみ形式で表示する。
 */
export const ReleaseDetailSection: React.FC<ReleaseDetailSectionProps> = ({
  releases,
}) => {
  const [expandedReleases, setExpandedReleases] = useState<Set<string>>(
    new Set()
  );

  // リリースがない場合
  if (releases.length === 0) {
    return null;
  }

  const toggleRelease = (releaseId: string) => {
    setExpandedReleases((prev) => {
      const next = new Set(prev);
      if (next.has(releaseId)) {
        next.delete(releaseId);
      } else {
        next.add(releaseId);
      }
      return next;
    });
  };

  const getFileTypeIcon = (type: 'NEW' | 'MODIFIED') => {
    if (type === 'NEW') {
      return (
        <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-green-100 text-green-800">
          NEW
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800">
        MOD
      </span>
    );
  };

  return (
    <div className="mb-4">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
        リリース履歴 ({releases.length}件)
      </h4>
      <div className="space-y-2">
        {releases.map((release) => {
          const isExpanded = expandedReleases.has(release.releaseId);

          return (
            <div
              key={release.releaseId}
              className="border border-gray-200 rounded-lg overflow-hidden"
            >
              {/* ヘッダー（クリックで開閉） */}
              <button
                onClick={() => toggleRelease(release.releaseId)}
                className="w-full flex items-center justify-between p-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left"
              >
                <div className="flex items-center">
                  <svg
                    className={`w-4 h-4 text-gray-400 mr-2 transition-transform ${
                      isExpanded ? 'transform rotate-90' : ''
                    }`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                  <span className="text-sm font-medium text-gray-700">
                    {release.releaseId}
                  </span>
                  <span className="ml-2 text-xs text-gray-500">
                    {release.date}
                  </span>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-xs text-gray-500">
                    {release.fileCount}ファイル
                  </span>
                  <span className="text-xs text-gray-400">
                    by {release.executor}
                  </span>
                </div>
              </button>

              {/* 詳細コンテンツ */}
              {isExpanded && (
                <div className="p-3 border-t border-gray-200 bg-white">
                  {/* リリースファイル一覧 */}
                  {release.files.length > 0 && (
                    <div className="mb-3">
                      <h5 className="text-xs font-medium text-gray-500 mb-2">
                        リリースファイル
                      </h5>
                      <div className="overflow-x-auto">
                        <table className="min-w-full text-sm">
                          <thead>
                            <tr className="border-b border-gray-100">
                              <th className="text-left py-1 px-2 text-xs font-medium text-gray-500">
                                種別
                              </th>
                              <th className="text-left py-1 px-2 text-xs font-medium text-gray-500">
                                ファイル
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {release.files.map((file, idx) => (
                              <tr
                                key={idx}
                                className="border-b border-gray-50 last:border-0"
                              >
                                <td className="py-1.5 px-2">
                                  {getFileTypeIcon(file.type)}
                                </td>
                                <td className="py-1.5 px-2">
                                  <code className="text-xs text-gray-600 bg-gray-50 px-1 py-0.5 rounded">
                                    {file.path}
                                  </code>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* 変更内容 */}
                  {release.changes && release.changes.length > 0 && (
                    <div>
                      <h5 className="text-xs font-medium text-gray-500 mb-2">
                        変更内容
                      </h5>
                      <ul className="space-y-1">
                        {release.changes.map((change, idx) => (
                          <li
                            key={idx}
                            className="flex items-start text-sm text-gray-600"
                          >
                            <span className="text-gray-400 mr-2">•</span>
                            <span>{change}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* 概要 */}
                  {release.summary && !release.changes?.length && (
                    <div>
                      <h5 className="text-xs font-medium text-gray-500 mb-1">
                        概要
                      </h5>
                      <p className="text-sm text-gray-600">{release.summary}</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
