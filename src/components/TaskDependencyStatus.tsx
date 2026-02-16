import React from 'react';

/**
 * 依存タスク情報
 */
export interface DependencyInfo {
  /** 依存タスクID */
  taskId: string;
  /** 依存タスクのステータス */
  status: string;
  /** 完了済みかどうか */
  isCompleted: boolean;
}

/**
 * タスク依存状態
 */
export interface TaskDependencyState {
  /** このタスクがブロックされているか */
  isBlocked: boolean;
  /** 依存タスク総数 */
  totalDependencies: number;
  /** 完了済み依存タスク数 */
  completedDependencies: number;
  /** 依存タスク詳細リスト */
  dependencies: DependencyInfo[];
}

interface TaskDependencyStatusProps {
  /** 依存状態 */
  dependencyState: TaskDependencyState | null;
  /** コンパクト表示（アイコンのみ） */
  compact?: boolean;
  /** クラス名 */
  className?: string;
}

/**
 * タスク依存関係ビジュアル表示コンポーネント
 *
 * タスクの依存関係状態を視覚的に表示します。
 * - ブロック中（🔒）: 依存タスクが未完了
 * - 実行可能（✅）: すべての依存タスクが完了
 * - 依存なし（-）: 依存タスクなし
 *
 * 依存タスクの完了数/総数をプログレスバーで表現します。
 */
export const TaskDependencyStatus: React.FC<TaskDependencyStatusProps> = ({
  dependencyState,
  compact = false,
  className = '',
}) => {
  // 依存関係がない場合
  if (!dependencyState || dependencyState.totalDependencies === 0) {
    return (
      <div className={`flex items-center ${className}`} title="依存タスクなし">
        {compact ? (
          <span className="text-gray-400 text-xs">-</span>
        ) : (
          <span className="text-xs text-gray-500">依存なし</span>
        )}
      </div>
    );
  }

  const { isBlocked, totalDependencies, completedDependencies, dependencies } =
    dependencyState;
  const progressPercent =
    totalDependencies > 0
      ? Math.round((completedDependencies / totalDependencies) * 100)
      : 0;

  // ツールチップ用の依存タスクリスト
  const tooltipText = dependencies
    .map((dep) => `${dep.taskId} (${dep.status})`)
    .join('\n');

  // ブロック中
  if (isBlocked) {
    return (
      <div
        className={`flex items-center gap-1 ${className}`}
        title={`ブロック中\n依存: ${completedDependencies}/${totalDependencies} 完了\n${tooltipText}`}
      >
        {/* ブロックアイコン */}
        <svg
          className="w-4 h-4 text-red-500 flex-shrink-0"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path
            fillRule="evenodd"
            d="M5 9V7a5 5 0 0110 0v2a2 2 0 012 2v5a2 2 0 01-2 2H5a2 2 0 01-2-2v-5a2 2 0 012-2zm8-2v2H7V7a3 3 0 016 0z"
            clipRule="evenodd"
          />
        </svg>

        {!compact && (
          <>
            {/* プログレスバー */}
            <div className="flex-1 min-w-[60px] max-w-[100px]">
              <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className="h-full bg-red-400 transition-all duration-300"
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
            </div>

            {/* 完了数表示 */}
            <span className="text-xs text-red-600 font-medium whitespace-nowrap">
              {completedDependencies}/{totalDependencies}
            </span>
          </>
        )}
      </div>
    );
  }

  // 実行可能（すべての依存タスク完了）
  return (
    <div
      className={`flex items-center gap-1 ${className}`}
      title={`実行可能\n依存: ${completedDependencies}/${totalDependencies} 完了\n${tooltipText}`}
    >
      {/* チェックアイコン */}
      <svg
        className="w-4 h-4 text-green-500 flex-shrink-0"
        fill="currentColor"
        viewBox="0 0 20 20"
      >
        <path
          fillRule="evenodd"
          d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
          clipRule="evenodd"
        />
      </svg>

      {!compact && (
        <>
          {/* プログレスバー（全完了） */}
          <div className="flex-1 min-w-[60px] max-w-[100px]">
            <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
              <div className="h-full bg-green-400 w-full transition-all duration-300" />
            </div>
          </div>

          {/* 完了数表示 */}
          <span className="text-xs text-green-600 font-medium whitespace-nowrap">
            {completedDependencies}/{totalDependencies}
          </span>
        </>
      )}
    </div>
  );
};
