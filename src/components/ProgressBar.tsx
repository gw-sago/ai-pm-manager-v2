import React from 'react';

interface ProgressBarProps {
  value: number;
  max: number;
  color?: 'green' | 'blue' | 'yellow' | 'red' | 'purple';
  showLabel?: boolean;
  animated?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

/**
 * 進捗バーコンポーネント
 *
 * 進捗率を視覚的に表示します。
 * アニメーション付きでスムーズに変化します。
 */
export const ProgressBar: React.FC<ProgressBarProps> = ({
  value,
  max,
  color = 'green',
  showLabel = true,
  animated = true,
  size = 'md',
}) => {
  const percentage = max > 0 ? Math.round((value / max) * 100) : 0;

  const colorClasses = {
    green: 'bg-green-500',
    blue: 'bg-blue-500',
    yellow: 'bg-yellow-500',
    red: 'bg-red-500',
    purple: 'bg-purple-500',
  };

  const sizeClasses = {
    sm: 'h-1.5',
    md: 'h-2.5',
    lg: 'h-4',
  };

  return (
    <div className="w-full">
      {showLabel && (
        <div className="flex justify-between items-center mb-1">
          <span className="text-sm font-medium text-gray-700">
            進捗率
          </span>
          <span className="text-sm font-semibold text-gray-900">
            {percentage}%
          </span>
        </div>
      )}
      <div className={`w-full bg-gray-200 rounded-full ${sizeClasses[size]} overflow-hidden`}>
        <div
          className={`${sizeClasses[size]} ${colorClasses[color]} rounded-full ${
            animated ? 'transition-all duration-500 ease-out' : ''
          }`}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showLabel && (
        <div className="flex justify-end mt-1">
          <span className="text-xs text-gray-500">
            {value} / {max} タスク完了
          </span>
        </div>
      )}
    </div>
  );
};
