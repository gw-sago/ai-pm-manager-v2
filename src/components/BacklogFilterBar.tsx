/**
 * BacklogFilterBar - バックログフィルタUIコンポーネント
 *
 * バックログ一覧のフィルタ・ソート機能を提供するUIコンポーネント。
 * - 優先度フィルタ（High/Medium/Low）
 * - ステータスフィルタ（TODO/IN_PROGRESS/DONE等）
 * - プロジェクト横断検索
 * - ソート機能（優先度順/作成日順/ステータス順）
 * - フィルタリセットボタン
 *
 * @module BacklogFilterBar
 * @created 2026-02-02
 * @order ORDER_021
 * @task TASK_327
 */

import React, { useCallback, useMemo } from 'react';
import type { BacklogFilters } from '../main/services/DashboardService';

// =============================================================================
// 型定義
// =============================================================================

/**
 * プロジェクト情報
 */
export interface ProjectOption {
  id: string;
  name: string;
}

/**
 * BacklogFilterBarのProps
 */
export interface BacklogFilterBarProps {
  /** 現在のフィルタ状態 */
  filters: BacklogFilters;
  /** フィルタ変更時のコールバック */
  onFiltersChange: (filters: BacklogFilters) => void;
  /** 利用可能なプロジェクト一覧 */
  projects?: ProjectOption[];
  /** 利用可能なステータス一覧 */
  availableStatuses?: string[];
  /** ローディング状態 */
  isLoading?: boolean;
  /** コンパクト表示モード */
  compact?: boolean;
}

// =============================================================================
// 定数
// =============================================================================

/** 優先度オプション */
const PRIORITY_OPTIONS: Array<{ value: 'High' | 'Medium' | 'Low'; label: string; color: string }> = [
  { value: 'High', label: 'High', color: 'bg-red-100 text-red-700 border-red-200' },
  { value: 'Medium', label: 'Medium', color: 'bg-yellow-100 text-yellow-700 border-yellow-200' },
  { value: 'Low', label: 'Low', color: 'bg-green-100 text-green-700 border-green-200' },
];

/** デフォルトステータスオプション */
const DEFAULT_STATUS_OPTIONS = ['TODO', 'IN_PROGRESS', 'DONE', 'BLOCKED', 'CANCELLED'];

/** ソートオプション */
const SORT_OPTIONS: Array<{ value: BacklogFilters['sortBy']; label: string }> = [
  { value: 'priority', label: '優先度順' },
  { value: 'createdAt', label: '作成日順' },
  { value: 'status', label: 'ステータス順' },
  { value: 'sortOrder', label: '並び順' },
];

/** ソート順オプション */
const SORT_ORDER_OPTIONS: Array<{ value: 'asc' | 'desc'; label: string }> = [
  { value: 'desc', label: '降順' },
  { value: 'asc', label: '昇順' },
];

// =============================================================================
// サブコンポーネント
// =============================================================================

/**
 * フィルタチップ（選択可能なピル形状のボタン）
 */
interface FilterChipProps {
  label: string;
  isSelected: boolean;
  onClick: () => void;
  colorClass?: string;
  disabled?: boolean;
}

const FilterChip: React.FC<FilterChipProps> = ({
  label,
  isSelected,
  onClick,
  colorClass = '',
  disabled = false,
}) => {
  const baseClasses = `
    inline-flex items-center px-2.5 py-1 text-xs font-medium rounded-full
    border transition-all duration-150 cursor-pointer select-none
  `;

  const selectedClasses = isSelected
    ? `${colorClass || 'bg-blue-100 text-blue-700 border-blue-300'} ring-1 ring-offset-1 ring-blue-400`
    : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100';

  const disabledClasses = disabled ? 'opacity-50 cursor-not-allowed' : '';

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`${baseClasses} ${selectedClasses} ${disabledClasses}`}
    >
      {isSelected && (
        <svg className="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      )}
      {label}
    </button>
  );
};

/**
 * フィルタセクション（ラベル付きグループ）
 */
interface FilterSectionProps {
  label: string;
  children: React.ReactNode;
  compact?: boolean;
}

const FilterSection: React.FC<FilterSectionProps> = ({ label, children, compact = false }) => {
  return (
    <div className={compact ? 'flex items-center gap-2' : ''}>
      <span className={`text-xs font-medium text-gray-500 ${compact ? '' : 'block mb-1.5'}`}>
        {label}
      </span>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
};

// =============================================================================
// メインコンポーネント
// =============================================================================

/**
 * バックログフィルタバーコンポーネント
 *
 * バックログ一覧のフィルタ・ソート機能を提供します。
 *
 * @example
 * ```tsx
 * const [filters, setFilters] = useState<BacklogFilters>({});
 *
 * <BacklogFilterBar
 *   filters={filters}
 *   onFiltersChange={setFilters}
 *   projects={[{ id: 'proj1', name: 'Project 1' }]}
 * />
 * ```
 */
export const BacklogFilterBar: React.FC<BacklogFilterBarProps> = ({
  filters,
  onFiltersChange,
  projects = [],
  availableStatuses = DEFAULT_STATUS_OPTIONS,
  isLoading = false,
  compact = false,
}) => {
  /**
   * フィルタがアクティブかどうか
   */
  const hasActiveFilters = useMemo(() => {
    return (
      (filters.priority && filters.priority.length > 0) ||
      (filters.status && filters.status.length > 0) ||
      filters.projectId ||
      filters.sortBy
    );
  }, [filters]);

  /**
   * 優先度フィルタのトグル
   */
  const handlePriorityToggle = useCallback(
    (priority: 'High' | 'Medium' | 'Low') => {
      const currentPriorities = filters.priority || [];
      const newPriorities = currentPriorities.includes(priority)
        ? currentPriorities.filter((p) => p !== priority)
        : [...currentPriorities, priority];

      onFiltersChange({
        ...filters,
        priority: newPriorities.length > 0 ? newPriorities : undefined,
      });
    },
    [filters, onFiltersChange]
  );

  /**
   * ステータスフィルタのトグル
   */
  const handleStatusToggle = useCallback(
    (status: string) => {
      const currentStatuses = filters.status || [];
      const newStatuses = currentStatuses.includes(status)
        ? currentStatuses.filter((s) => s !== status)
        : [...currentStatuses, status];

      onFiltersChange({
        ...filters,
        status: newStatuses.length > 0 ? newStatuses : undefined,
      });
    },
    [filters, onFiltersChange]
  );

  /**
   * プロジェクトフィルタの変更
   */
  const handleProjectChange = useCallback(
    (projectId: string) => {
      onFiltersChange({
        ...filters,
        projectId: projectId || undefined,
      });
    },
    [filters, onFiltersChange]
  );

  /**
   * ソートの変更
   */
  const handleSortChange = useCallback(
    (sortBy: BacklogFilters['sortBy']) => {
      onFiltersChange({
        ...filters,
        sortBy: sortBy || undefined,
      });
    },
    [filters, onFiltersChange]
  );

  /**
   * ソート順の変更
   */
  const handleSortOrderChange = useCallback(
    (sortOrder: 'asc' | 'desc') => {
      onFiltersChange({
        ...filters,
        sortOrder,
      });
    },
    [filters, onFiltersChange]
  );

  /**
   * フィルタのリセット
   */
  const handleReset = useCallback(() => {
    onFiltersChange({});
  }, [onFiltersChange]);

  // コンパクトモード
  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-3 p-2 bg-gray-50 rounded-lg border border-gray-200">
        {/* 優先度フィルタ */}
        <FilterSection label="優先度:" compact>
          {PRIORITY_OPTIONS.map((option) => (
            <FilterChip
              key={option.value}
              label={option.label}
              isSelected={filters.priority?.includes(option.value) || false}
              onClick={() => handlePriorityToggle(option.value)}
              colorClass={option.color}
              disabled={isLoading}
            />
          ))}
        </FilterSection>

        <div className="w-px h-6 bg-gray-300" />

        {/* ステータスフィルタ */}
        <FilterSection label="ステータス:" compact>
          {availableStatuses.slice(0, 3).map((status) => (
            <FilterChip
              key={status}
              label={status}
              isSelected={filters.status?.includes(status) || false}
              onClick={() => handleStatusToggle(status)}
              disabled={isLoading}
            />
          ))}
        </FilterSection>

        {/* リセットボタン */}
        {hasActiveFilters && (
          <>
            <div className="w-px h-6 bg-gray-300" />
            <button
              type="button"
              onClick={handleReset}
              disabled={isLoading}
              className="text-xs text-gray-500 hover:text-gray-700 underline"
            >
              リセット
            </button>
          </>
        )}
      </div>
    );
  }

  // 通常モード
  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-4">
      {/* ヘッダー */}
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z"
            />
          </svg>
          フィルタ・ソート
        </h3>
        {hasActiveFilters && (
          <button
            type="button"
            onClick={handleReset}
            disabled={isLoading}
            className={`
              flex items-center gap-1 px-2 py-1 text-xs font-medium rounded
              text-gray-500 hover:text-gray-700 hover:bg-gray-100
              transition-colors
              ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}
            `}
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            リセット
          </button>
        )}
      </div>

      {/* フィルタセクション */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* 優先度フィルタ */}
        <FilterSection label="優先度">
          {PRIORITY_OPTIONS.map((option) => (
            <FilterChip
              key={option.value}
              label={option.label}
              isSelected={filters.priority?.includes(option.value) || false}
              onClick={() => handlePriorityToggle(option.value)}
              colorClass={option.color}
              disabled={isLoading}
            />
          ))}
        </FilterSection>

        {/* ステータスフィルタ */}
        <FilterSection label="ステータス">
          {availableStatuses.map((status) => (
            <FilterChip
              key={status}
              label={status}
              isSelected={filters.status?.includes(status) || false}
              onClick={() => handleStatusToggle(status)}
              disabled={isLoading}
            />
          ))}
        </FilterSection>

        {/* プロジェクトフィルタ */}
        {projects.length > 0 && (
          <FilterSection label="プロジェクト">
            <select
              value={filters.projectId || ''}
              onChange={(e) => handleProjectChange(e.target.value)}
              disabled={isLoading}
              className={`
                w-full px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg
                bg-white text-gray-700
                focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent
                ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}
              `}
            >
              <option value="">すべてのプロジェクト</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </FilterSection>
        )}

        {/* ソート */}
        <FilterSection label="ソート">
          <div className="flex gap-1.5 w-full">
            <select
              value={filters.sortBy || ''}
              onChange={(e) => handleSortChange(e.target.value as BacklogFilters['sortBy'])}
              disabled={isLoading}
              className={`
                flex-1 px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg
                bg-white text-gray-700
                focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent
                ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}
              `}
            >
              <option value="">デフォルト</option>
              {SORT_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            {filters.sortBy && (
              <select
                value={filters.sortOrder || 'desc'}
                onChange={(e) => handleSortOrderChange(e.target.value as 'asc' | 'desc')}
                disabled={isLoading}
                className={`
                  w-20 px-2 py-1.5 text-xs border border-gray-200 rounded-lg
                  bg-white text-gray-700
                  focus:outline-none focus:ring-2 focus:ring-blue-400 focus:border-transparent
                  ${isLoading ? 'opacity-50 cursor-not-allowed' : ''}
                `}
              >
                {SORT_ORDER_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            )}
          </div>
        </FilterSection>
      </div>

      {/* アクティブフィルタ表示 */}
      {hasActiveFilters && (
        <div className="flex flex-wrap items-center gap-2 pt-3 border-t border-gray-100">
          <span className="text-xs text-gray-400">適用中:</span>
          {filters.priority?.map((p) => (
            <span
              key={`active-priority-${p}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-blue-50 text-blue-600 rounded"
            >
              優先度: {p}
              <button
                type="button"
                onClick={() => handlePriorityToggle(p)}
                className="hover:text-blue-800"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </span>
          ))}
          {filters.status?.map((s) => (
            <span
              key={`active-status-${s}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-purple-50 text-purple-600 rounded"
            >
              ステータス: {s}
              <button
                type="button"
                onClick={() => handleStatusToggle(s)}
                className="hover:text-purple-800"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </span>
          ))}
          {filters.projectId && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-green-50 text-green-600 rounded">
              プロジェクト: {projects.find((p) => p.id === filters.projectId)?.name || filters.projectId}
              <button
                type="button"
                onClick={() => handleProjectChange('')}
                className="hover:text-green-800"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </span>
          )}
          {filters.sortBy && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] bg-gray-100 text-gray-600 rounded">
              ソート: {SORT_OPTIONS.find((o) => o.value === filters.sortBy)?.label || filters.sortBy}{' '}
              ({filters.sortOrder === 'asc' ? '昇順' : '降順'})
            </span>
          )}
        </div>
      )}
    </div>
  );
};

export default BacklogFilterBar;
