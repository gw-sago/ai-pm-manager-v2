import React from 'react';
import { TaskCard } from './TaskCard';
import type { TaskInfo } from '../preload';
import type { TaskDependencyState } from './TaskDependencyStatus';

interface TaskListProps {
  tasks: TaskInfo[];
  onTaskClick?: (task: TaskInfo) => void;
  emptyMessage?: string;
  dependencyStates?: Map<string, TaskDependencyState>;
}

/**
 * TASK一覧コンポーネント
 *
 * タスクの配列をTaskCardのリストとして表示します。
 * ORDER内で表示する場合や、全タスク一覧として表示する場合に使用。
 */
export const TaskList: React.FC<TaskListProps> = ({
  tasks,
  onTaskClick,
  emptyMessage = 'タスクがありません',
  dependencyStates,
}) => {
  if (tasks.length === 0) {
    return (
      <div className="text-center py-4 text-gray-500 text-sm">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {tasks.map((task) => (
        <TaskCard
          key={task.id}
          task={task}
          onClick={() => onTaskClick?.(task)}
          dependencyState={dependencyStates?.get(task.id)}
        />
      ))}
    </div>
  );
};
