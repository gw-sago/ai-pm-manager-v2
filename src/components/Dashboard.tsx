import React from 'react';
import type { Project } from '../preload';

interface DashboardProps {
  project: Project;
}

/**
 * プロジェクトヘッダーコンポーネント
 *
 * 選択されたプロジェクトの基本情報を表示します。
 * - プロジェクト名
 * - ステータス
 */
export const Dashboard: React.FC<DashboardProps> = ({ project }) => {
  if (!project.state) {
    // ORDER_016 FR-005: STATE.md不在時の動作対応
    // DBモードではSTATE.mdがなくてもDBからデータが取得されるため、
    // stateがnullの場合は一時的な状態（ロード中またはデータなし）として扱う
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="text-center py-8">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-gray-100 rounded-full mb-4">
            <svg
              className="w-6 h-6 text-gray-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
          </div>
          <h3 className="text-sm font-medium text-gray-900 mb-1">
            プロジェクトデータを読み込み中...
          </h3>
          <p className="text-xs text-gray-500">
            プロジェクトを選択し直すか、画面を更新してください
          </p>
        </div>
      </div>
    );
  }

  const { projectInfo } = project.state;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      {/* ヘッダー（プロジェクト名とステータス） */}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-gray-800">
          {project.name}
        </h2>
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
            projectInfo.status === 'COMPLETED'
              ? 'bg-green-100 text-green-800'
              : projectInfo.status === 'IN_PROGRESS'
              ? 'bg-blue-100 text-blue-800'
              : projectInfo.status === 'REVIEW'
              ? 'bg-yellow-100 text-yellow-800'
              : 'bg-gray-100 text-gray-800'
          }`}
        >
          {projectInfo.status}
        </span>
      </div>
    </div>
  );
};
