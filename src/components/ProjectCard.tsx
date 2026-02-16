import React from 'react';
import type { Project } from '../preload';

interface ProjectCardProps {
  project: Project;
  isSelected: boolean;
  onClick: () => void;
  /** コンパクト表示モード（サイドバー用） */
  compact?: boolean;
  /** サイドバー折りたたみ状態 */
  collapsed?: boolean;
  /** データソース（DBモードでは「未設定」警告を表示しない） */
  dataSource?: 'db' | 'file';
}

/**
 * ステータスに応じた色設定を返す
 */
const getStatusColor = (status: string): { bg: string; text: string; dot: string } => {
  switch (status) {
    case 'COMPLETED':
      return { bg: 'bg-green-100', text: 'text-green-800', dot: 'bg-green-500' };
    case 'IN_PROGRESS':
      return { bg: 'bg-blue-100', text: 'text-blue-800', dot: 'bg-blue-500' };
    case 'REVIEW':
      return { bg: 'bg-yellow-100', text: 'text-yellow-800', dot: 'bg-yellow-500' };
    case 'REWORK':
      return { bg: 'bg-orange-100', text: 'text-orange-800', dot: 'bg-orange-500' };
    case 'ON_HOLD':
      return { bg: 'bg-gray-100', text: 'text-gray-800', dot: 'bg-gray-500' };
    case 'PLANNING':
      return { bg: 'bg-purple-100', text: 'text-purple-800', dot: 'bg-purple-500' };
    case 'INITIAL':
      return { bg: 'bg-gray-100', text: 'text-gray-600', dot: 'bg-gray-400' };
    default:
      return { bg: 'bg-gray-100', text: 'text-gray-800', dot: 'bg-gray-500' };
  }
};

/**
 * ステータスの日本語表示を返す
 */
const getStatusLabel = (status: string): string => {
  switch (status) {
    case 'COMPLETED':
      return '完了';
    case 'IN_PROGRESS':
      return '進行中';
    case 'REVIEW':
      return 'レビュー中';
    case 'REWORK':
      return '差戻し';
    case 'ON_HOLD':
      return '保留';
    case 'PLANNING':
      return '計画中';
    case 'INITIAL':
      return '初期';
    default:
      return status;
  }
};

/**
 * アクティブORDER数を計算
 */
const getActiveOrderCount = (project: Project): { active: number; total: number } => {
  if (!project.state?.orders) {
    return { active: 0, total: 0 };
  }

  const total = project.state.orders.length;
  const active = project.state.orders.filter(
    (order) => order.status !== 'COMPLETED' && order.status !== 'CANCELLED'
  ).length;

  return { active, total };
};

/**
 * プロジェクトカードコンポーネント
 *
 * プロジェクト名、ステータス、アクティブORDER数を表示します。
 * 選択状態でハイライト表示されます。
 */
export const ProjectCard: React.FC<ProjectCardProps> = ({
  project,
  isSelected,
  onClick,
  compact = false,
  collapsed = false,
  dataSource = 'file',
}) => {
  const statusColor = getStatusColor(project.state?.projectInfo?.status || 'INITIAL');
  const orderCount = getActiveOrderCount(project);
  const status = project.state?.projectInfo?.status || 'INITIAL';

  // サイドバー折りたたみ時: 頭文字のみ表示
  if (collapsed) {
    const initial = project.name.charAt(0).toUpperCase();
    return (
      <button
        onClick={onClick}
        className={`relative w-10 h-10 flex items-center justify-center rounded-lg border transition-all duration-200 ${
          isSelected
            ? 'border-blue-500 bg-blue-100 ring-2 ring-blue-200'
            : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50'
        }`}
        title={project.name}
      >
        <span
          className={`text-sm font-bold ${
            isSelected ? 'text-blue-600' : 'text-gray-600'
          }`}
        >
          {initial}
        </span>
        {/* ステータスインジケータ */}
        <span
          className={`absolute bottom-0.5 right-0.5 w-2 h-2 rounded-full ${statusColor.dot}`}
        />
      </button>
    );
  }

  // コンパクト表示（サイドバー展開時）
  if (compact) {
    return (
      <button
        onClick={onClick}
        className={`w-full text-left p-2 rounded-md border transition-all duration-200 ${
          isSelected
            ? 'border-blue-500 bg-blue-50 ring-1 ring-blue-200'
            : 'border-transparent bg-white hover:bg-gray-50'
        }`}
      >
        <div className="flex items-center">
          {/* ステータスドット */}
          <span className={`w-2 h-2 rounded-full ${statusColor.dot} mr-2 flex-shrink-0`} />
          {/* プロジェクト名 */}
          <span
            className={`text-sm font-medium truncate ${
              isSelected ? 'text-blue-700' : 'text-gray-700'
            }`}
          >
            {project.name}
          </span>
          {/* ORDER数（簡易表示） */}
          {orderCount.active > 0 && (
            <span className="ml-auto text-xs text-gray-400 flex-shrink-0">
              {orderCount.active}
            </span>
          )}
        </div>
        {/* STATE.mdなし かつ stateもない かつ ファイルモードの場合のみ警告表示 */}
        {/* DBモードではSTATE.mdが不要なため警告を表示しない（ORDER_027: BACKLOG_069対応） */}
        {dataSource === 'file' && !project.hasStateFile && !project.state && (
          <div className="mt-1 text-xs text-amber-500 flex items-center">
            <svg
              className="w-3 h-3 mr-0.5"
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
            <span>未設定</span>
          </div>
        )}
      </button>
    );
  }

  // 通常表示（メインエリア用）
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-lg border transition-all duration-200 ${
        isSelected
          ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200'
          : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
      }`}
    >
      {/* ヘッダー行: プロジェクト名 + 選択バッジ */}
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900 truncate pr-2">
          {project.name}
        </h3>
        {isSelected && (
          <span className="flex-shrink-0 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-500 text-white">
            選択中
          </span>
        )}
      </div>

      {/* ステータス行 */}
      <div className="flex items-center mb-2">
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColor.bg} ${statusColor.text}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${statusColor.dot} mr-1.5`} />
          {getStatusLabel(status)}
        </span>
      </div>

      {/* ORDER情報行 */}
      <div className="flex items-center text-xs text-gray-500">
        <svg
          className="w-4 h-4 mr-1"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
          />
        </svg>
        <span>
          アクティブORDER: {orderCount.active} / {orderCount.total}
        </span>
      </div>

      {/* STATE.mdなしの場合の警告（ファイルモードのみ） */}
      {/* DBモードではSTATE.mdが不要なため警告を表示しない（ORDER_027: BACKLOG_069対応） */}
      {dataSource === 'file' && !project.hasStateFile && (
        <div className="mt-2 text-xs text-amber-600 flex items-center">
          <svg
            className="w-3.5 h-3.5 mr-1"
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
          <span>STATE.mdなし</span>
        </div>
      )}
    </button>
  );
};
