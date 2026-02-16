import React, { useMemo, useCallback, useState, useEffect, useRef } from 'react';
import type { TaskInfo, OrderInfo } from '../preload';
import { useTaskDependencyUpdates } from '../hooks/useTaskDependencyUpdates';

interface TaskDependencyViewProps {
  order: OrderInfo;
  onTaskClick?: (task: TaskInfo) => void;
  /** 折りたたみ可能にするかどうか */
  collapsible?: boolean;
  /** デフォルトで展開するかどうか（collapsible=trueの場合のみ有効） */
  defaultExpanded?: boolean;
  /** ORDER_119: プロジェクトID（ステップインジケータ用） */
  projectId?: string;
}

/** ORDER_119: ステップ情報キャッシュ */
interface StepInfo {
  currentStep: string | null;
  stepIndex: number;
  totalSteps: number;
}

/**
 * タスクステータスに応じた色定義
 */
const statusColors: Record<string, { bg: string; border: string; text: string }> = {
  QUEUED: {
    bg: 'bg-gray-200',
    border: 'border-gray-400',
    text: 'text-gray-700',
  },
  BLOCKED: {
    bg: 'bg-red-100',
    border: 'border-red-400',
    text: 'text-red-700',
  },
  IN_PROGRESS: {
    bg: 'bg-blue-200',
    border: 'border-blue-400',
    text: 'text-blue-700',
  },
  IN_REVIEW: {
    bg: 'bg-orange-200',
    border: 'border-orange-400',
    text: 'text-orange-700',
  },
  DONE: {
    bg: 'bg-green-100',
    border: 'border-green-400',
    text: 'text-green-700',
  },
  REWORK: {
    bg: 'bg-red-200',
    border: 'border-red-600',
    text: 'text-red-800',
  },
  COMPLETED: {
    bg: 'bg-green-200',
    border: 'border-green-500',
    text: 'text-green-800',
  },
  CANCELLED: {
    bg: 'bg-gray-300',
    border: 'border-gray-500',
    text: 'text-gray-500',
  },
  REJECTED: {
    bg: 'bg-red-300',
    border: 'border-red-700',
    text: 'text-red-900',
  },
  SKIPPED: {
    bg: 'bg-gray-100',
    border: 'border-gray-300',
    text: 'text-gray-400',
  },
};

/**
 * ステータスアイコンコンポーネント
 */
const StatusIcon: React.FC<{ status: string; className?: string }> = ({ status, className = 'w-4 h-4' }) => {
  switch (status) {
    case 'COMPLETED':
      return (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'IN_PROGRESS':
      return (
        <svg className={`${className} animate-spin`} fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
          />
        </svg>
      );
    case 'BLOCKED':
      return (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M13.477 14.89A6 6 0 015.11 6.524l8.367 8.368zm1.414-1.414L6.524 5.11a6 6 0 018.367 8.367zM18 10a8 8 0 11-16 0 8 8 0 0116 0z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'DONE':
      return (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path d="M9 2a1 1 0 000 2h2a1 1 0 100-2H9z" />
          <path
            fillRule="evenodd"
            d="M4 5a2 2 0 012-2 3 3 0 003 3h2a3 3 0 003-3 2 2 0 012 2v11a2 2 0 01-2 2H6a2 2 0 01-2-2V5zm9.707 5.707a1 1 0 00-1.414-1.414L9 12.586l-1.293-1.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'REWORK':
      return (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'IN_REVIEW':
      return (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path d="M9 4.804A7.968 7.968 0 005.5 4c-1.255 0-2.443.29-3.5.804v10A7.969 7.969 0 015.5 14c1.669 0 3.218.51 4.5 1.385A7.962 7.962 0 0114.5 14c1.255 0 2.443.29 3.5.804v-10A7.968 7.968 0 0014.5 4c-1.255 0-2.443.29-3.5.804V12a1 1 0 11-2 0V4.804z" />
        </svg>
      );
    case 'CANCELLED':
      return (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'REJECTED':
      return (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zM7 9a1 1 0 000 2h6a1 1 0 100-2H7z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'SKIPPED':
      return (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z"
            clipRule="evenodd"
          />
        </svg>
      );
    case 'QUEUED':
    default:
      return (
        <svg className={className} fill="currentColor" viewBox="0 0 20 20">
          <path
            fillRule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z"
            clipRule="evenodd"
          />
        </svg>
      );
  }
};

/**
 * タスクノードの位置情報
 */
interface TaskNode {
  task: TaskInfo;
  level: number;  // 横方向の位置（依存深度）
  row: number;    // 縦方向の位置（同レベル内の順序）
  x: number;      // 実際のX座標
  y: number;      // 実際のY座標
}

/**
 * 依存関係の線情報
 */
interface DependencyLine {
  fromId: string;
  toId: string;
  fromX: number;
  fromY: number;
  toX: number;
  toY: number;
}

// 定数定義
const NODE_WIDTH = 160;
const NODE_HEIGHT = 90; // ORDER_119: ステップインジケータ分拡大（70→90）
const HORIZONTAL_GAP = 60;
const VERTICAL_GAP = 20;
const PADDING = 20;

// ORDER_119: 簡易ステップ定義（UIに表示する主要ステップ4つ）
const EXECUTION_STEPS_SHORT = [
  { key: 'assign', label: '割当' },
  { key: 'lock', label: 'Lock' },
  { key: 'exec', label: '実行' },
  { key: 'report', label: '報告' },
] as const;

/**
 * タスクの依存関係を解析してレベルに配置する
 */
function analyzeTaskDependencies(tasks: TaskInfo[]): { nodes: TaskNode[]; lines: DependencyLine[] } {
  if (tasks.length === 0) {
    return { nodes: [], lines: [] };
  }

  // タスクIDからタスクへのマップを作成
  const taskMap = new Map<string, TaskInfo>();
  tasks.forEach(task => taskMap.set(task.id, task));

  // 各タスクのレベル（依存深度）を計算
  const levelMap = new Map<string, number>();

  // 依存がないタスクはレベル0
  const calculateLevel = (taskId: string, visited: Set<string> = new Set()): number => {
    if (levelMap.has(taskId)) {
      return levelMap.get(taskId)!;
    }

    if (visited.has(taskId)) {
      // 循環依存の場合
      return 0;
    }

    visited.add(taskId);
    const task = taskMap.get(taskId);

    if (!task || task.dependencies.length === 0 || (task.dependencies.length === 1 && task.dependencies[0] === '-')) {
      levelMap.set(taskId, 0);
      return 0;
    }

    // 依存タスクの最大レベル + 1
    let maxDepLevel = 0;
    for (const depId of task.dependencies) {
      if (depId && depId !== '-' && taskMap.has(depId)) {
        const depLevel = calculateLevel(depId, new Set(visited));
        maxDepLevel = Math.max(maxDepLevel, depLevel + 1);
      }
    }

    levelMap.set(taskId, maxDepLevel);
    return maxDepLevel;
  };

  // 全タスクのレベルを計算
  tasks.forEach(task => calculateLevel(task.id));

  // レベルごとにタスクをグループ化
  const levelGroups = new Map<number, TaskInfo[]>();
  tasks.forEach(task => {
    const level = levelMap.get(task.id) || 0;
    if (!levelGroups.has(level)) {
      levelGroups.set(level, []);
    }
    levelGroups.get(level)!.push(task);
  });

  // ノードの位置を計算
  const nodes: TaskNode[] = [];
  levelGroups.forEach((tasksInLevel, level) => {
    tasksInLevel.forEach((task, row) => {
      const x = PADDING + level * (NODE_WIDTH + HORIZONTAL_GAP);
      const y = PADDING + row * (NODE_HEIGHT + VERTICAL_GAP);
      nodes.push({ task, level, row, x, y });
    });
  });

  // ノードIDからノードへのマップ
  const nodeMap = new Map<string, TaskNode>();
  nodes.forEach(node => nodeMap.set(node.task.id, node));

  // 依存関係の線を生成
  const lines: DependencyLine[] = [];
  nodes.forEach(node => {
    const deps = node.task.dependencies.filter(d => d && d !== '-');
    deps.forEach(depId => {
      const fromNode = nodeMap.get(depId);
      if (fromNode) {
        lines.push({
          fromId: depId,
          toId: node.task.id,
          fromX: fromNode.x + NODE_WIDTH,
          fromY: fromNode.y + NODE_HEIGHT / 2,
          toX: node.x,
          toY: node.y + NODE_HEIGHT / 2,
        });
      }
    });
  });

  return { nodes, lines };
}

/**
 * ORDER_119: ステップインジケータコンポーネント（IN_PROGRESSノード用）
 */
const StepIndicator: React.FC<{ stepInfo: StepInfo }> = ({ stepInfo }) => {
  return (
    <div className="flex items-center gap-0.5 mt-1" title={`Step ${stepInfo.stepIndex + 1}/${stepInfo.totalSteps}`}>
      {EXECUTION_STEPS_SHORT.map((step, i) => {
        // 4ステップに簡約: assign(0-1), lock(2), exec(3), report(4-7)
        const mappedIndex = i === 0 ? 1 : i === 1 ? 2 : i === 2 ? 3 : 5;
        const isCompleted = stepInfo.stepIndex > mappedIndex;
        const isCurrent = stepInfo.stepIndex === mappedIndex ||
          (i === 0 && stepInfo.stepIndex <= 1) ||
          (i === 3 && stepInfo.stepIndex >= 4 && stepInfo.stepIndex <= 7);
        return (
          <React.Fragment key={step.key}>
            {i > 0 && <div className={`w-2 h-px ${isCompleted ? 'bg-blue-400' : 'bg-gray-300'}`} />}
            <div
              className={`w-3 h-3 rounded-full flex items-center justify-center text-[6px] font-bold ${
                isCompleted ? 'bg-blue-500 text-white' :
                isCurrent ? 'bg-blue-400 text-white animate-pulse' :
                'bg-gray-300 text-gray-500'
              }`}
              title={step.label}
            >
              {isCompleted ? '✓' : (i + 1)}
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
};

/**
 * タスクノードコンポーネント
 */
const TaskNodeComponent: React.FC<{
  node: TaskNode;
  onClick?: () => void;
  stepInfo?: StepInfo;
}> = ({ node, onClick, stepInfo }) => {
  const colors = statusColors[node.task.status] || statusColors.QUEUED;
  const isCancelled = node.task.status === 'CANCELLED';
  const isSkipped = node.task.status === 'SKIPPED';
  const isRejected = node.task.status === 'REJECTED';
  const isRework = node.task.status === 'REWORK';
  const isInProgress = node.task.status === 'IN_PROGRESS';
  const isInactive = isCancelled || isSkipped;

  return (
    <div
      className={`absolute rounded-lg border-2 ${colors.bg} ${colors.border} shadow-sm cursor-pointer hover:shadow-md transition-shadow ${isInactive ? 'opacity-60' : ''} ${isRework ? 'border-dashed' : ''}`}
      style={{
        left: node.x,
        top: node.y,
        width: NODE_WIDTH,
        height: NODE_HEIGHT,
      }}
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          onClick?.();
        }
      }}
    >
      <div className="flex flex-col items-center justify-center h-full p-2">
        <div className="flex items-center space-x-1">
          <StatusIcon status={node.task.status} className={`w-4 h-4 ${colors.text}`} />
          <span className={`text-xs font-mono font-semibold text-gray-700 ${isCancelled || isRejected ? 'line-through' : ''}`}>
            {node.task.id}
          </span>
        </div>
        <div
          className={`text-[10px] mt-1 px-1 text-gray-600 truncate max-w-full text-center leading-tight ${isCancelled || isRejected ? 'line-through' : ''}`}
          title={node.task.title}
        >
          {node.task.title || 'No title'}
        </div>
        {/* ORDER_119: IN_PROGRESSノードにステップインジケータ表示 */}
        {isInProgress && stepInfo ? (
          <StepIndicator stepInfo={stepInfo} />
        ) : (
          <div
            className={`text-[9px] mt-0.5 px-1.5 py-0.5 rounded ${colors.bg} ${colors.text} font-medium`}
          >
            {node.task.status}
          </div>
        )}
      </div>
    </div>
  );
};

/**
 * SVG矢印線コンポーネント
 */
const DependencyArrow: React.FC<{ line: DependencyLine }> = ({ line }) => {
  // ベジェ曲線でスムーズな接続線を描画
  const midX = (line.fromX + line.toX) / 2;

  // 矢印の三角形サイズ
  const arrowSize = 8;

  return (
    <g>
      {/* 接続線 */}
      <path
        d={`M ${line.fromX} ${line.fromY} C ${midX} ${line.fromY}, ${midX} ${line.toY}, ${line.toX - arrowSize} ${line.toY}`}
        fill="none"
        stroke="#9CA3AF"
        strokeWidth="2"
        strokeLinecap="round"
      />
      {/* 矢印ヘッド */}
      <polygon
        points={`${line.toX},${line.toY} ${line.toX - arrowSize},${line.toY - arrowSize / 2} ${line.toX - arrowSize},${line.toY + arrowSize / 2}`}
        fill="#9CA3AF"
      />
    </g>
  );
};

/**
 * TASK依存関係ビューコンポーネント
 *
 * 選択されたORDERのTASK一覧を依存関係に基づいてフローチャート風に表示します。
 * 直列/並列/合流の関係を視覚的に表現し、各TASKはステータスに応じて色分けされます。
 *
 * ORDER_126 / TASK_1120: ノードクリック時にTaskDetailPanelをモーダル表示。
 * 依存タスク間のクリック遷移もサポート。
 */
export const TaskDependencyView: React.FC<TaskDependencyViewProps> = ({
  order,
  onTaskClick,
  collapsible = false,
  defaultExpanded = true,
  projectId,
}) => {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  // ORDER_140 TASK_1167: 依存関係リアルタイム更新フック
  const { dependencyMap, lastUpdate, isLoading: isDependencyLoading, refresh: refreshDependencies } = useTaskDependencyUpdates(
    projectId || null,
    order?.id || null
  );

  // ORDER_119: IN_PROGRESSタスクのステップ情報をポーリング取得
  const [stepInfoMap, setStepInfoMap] = useState<Map<string, StepInfo>>(new Map());
  const stepPollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const inProgressTaskIds = useMemo(
    () => order.tasks.filter(t => t.status === 'IN_PROGRESS').map(t => t.id),
    [order.tasks]
  );

  useEffect(() => {
    if (!projectId || inProgressTaskIds.length === 0) {
      setStepInfoMap(new Map());
      return;
    }

    let cancelled = false;

    const fetchSteps = async () => {
      const newMap = new Map<string, StepInfo>();
      for (const taskId of inProgressTaskIds) {
        if (cancelled) return;
        try {
          const result = await window.electronAPI.getTaskExecutionSteps(projectId, taskId);
          if (result) {
            newMap.set(taskId, {
              currentStep: result.currentStep,
              stepIndex: result.stepIndex,
              totalSteps: result.totalSteps,
            });
          }
        } catch {
          // ステップ取得失敗は無視（インジケータ非表示になるだけ）
        }
      }
      if (!cancelled) {
        setStepInfoMap(newMap);
        // 次回ポーリング（5秒後）
        stepPollRef.current = setTimeout(fetchSteps, 5000);
      }
    };

    fetchSteps();

    return () => {
      cancelled = true;
      if (stepPollRef.current) {
        clearTimeout(stepPollRef.current);
        stepPollRef.current = null;
      }
    };
  }, [projectId, inProgressTaskIds.join(',')]);

  // 依存関係を解析（dependencyMapからリアルタイムステータスを反映）
  const { nodes, lines } = useMemo(() => {
    // dependencyMapがある場合、タスクのステータスをリアルタイム情報で更新
    const enrichedTasks = order.tasks.map(task => {
      const depStatus = dependencyMap.get(task.id);
      if (depStatus) {
        return { ...task, status: depStatus.status };
      }
      return task;
    });
    return analyzeTaskDependencies(enrichedTasks);
  }, [order.tasks, dependencyMap]);

  // 依存関係があるかどうか（実際に依存線が存在するか）
  const hasDependencies = lines.length > 0;

  // ビューポートのサイズを計算
  const viewportSize = useMemo(() => {
    if (nodes.length === 0) {
      return { width: 400, height: 200 };
    }

    const maxX = Math.max(...nodes.map(n => n.x + NODE_WIDTH));
    const maxY = Math.max(...nodes.map(n => n.y + NODE_HEIGHT));

    return {
      width: Math.max(400, maxX + PADDING),
      height: Math.max(200, maxY + PADDING),
    };
  }, [nodes]);

  // ORDER_135 TASK_1152: ノードクリック時は親コンポーネント（Layout経由）にイベント伝播
  const handleTaskClick = useCallback((task: TaskInfo) => {
    // onTaskClickコールバックを呼び出し（Layoutに状態管理を委譲）
    onTaskClick?.(task);
  }, [onTaskClick]);

  // タスクがない場合
  if (order.tasks.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="text-center py-8">
          <div className="inline-flex items-center justify-center w-12 h-12 bg-gray-100 rounded-full mb-4">
            <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
              />
            </svg>
          </div>
          <h3 className="text-sm font-medium text-gray-900 mb-1">
            タスクがありません
          </h3>
          <p className="text-xs text-gray-500">
            このORDERにはタスクが登録されていません
          </p>
        </div>
      </div>
    );
  }

  // 折りたたみボタンのトグルハンドラ
  const handleToggleExpand = () => {
    if (collapsible) {
      setIsExpanded(!isExpanded);
    }
  };

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200">
      {/* ヘッダー */}
      <div
        className={`flex items-center justify-between p-4 ${isExpanded ? 'border-b border-gray-200' : ''} ${collapsible ? 'cursor-pointer hover:bg-gray-50' : ''}`}
        onClick={handleToggleExpand}
        role={collapsible ? 'button' : undefined}
        tabIndex={collapsible ? 0 : undefined}
        onKeyDown={collapsible ? (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            handleToggleExpand();
          }
        } : undefined}
      >
        <div className="flex items-center space-x-3">
          {/* 折りたたみアイコン */}
          {collapsible && (
            <svg
              className={`w-5 h-5 text-gray-500 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          )}
          <h2 className="text-lg font-semibold text-gray-800">
            TASK依存関係
          </h2>
          <span className="text-sm text-gray-500">
            {order.id} - {order.title || 'タイトルなし'}
          </span>
          {/* 依存関係なしバッジ */}
          {!hasDependencies && (
            <span className="px-2 py-0.5 text-xs bg-gray-100 text-gray-500 rounded-full">
              依存関係なし
            </span>
          )}
          {/* ORDER_140 TASK_1167: リアルタイム更新インジケータ */}
          {isDependencyLoading && (
            <span className="flex items-center text-xs text-blue-500">
              <svg className="animate-spin h-3 w-3 mr-1" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              更新中
            </span>
          )}
        </div>
        <div className="flex items-center space-x-3">
          <div className="text-xs text-gray-500">
            {order.tasks.length} タスク
          </div>
          {/* ORDER_140 TASK_1167: 最終更新時刻表示 */}
          {lastUpdate && !isDependencyLoading && (
            <div className="text-xs text-gray-400" title={`最終更新: ${lastUpdate.toLocaleString('ja-JP')}`}>
              {new Date().getTime() - lastUpdate.getTime() < 60000
                ? '最新'
                : `${Math.floor((new Date().getTime() - lastUpdate.getTime()) / 60000)}分前`}
            </div>
          )}
        </div>
      </div>

      {/* 展開時のコンテンツ */}
      {isExpanded && (
        <>
          {/* 依存関係グラフ */}
          <div
            className="relative overflow-auto p-4"
            style={{ minHeight: viewportSize.height + 40 }}
          >
            {/* SVG層（矢印線） */}
            <svg
              className="absolute inset-0 pointer-events-none"
              style={{
                width: viewportSize.width,
                height: viewportSize.height,
              }}
            >
              {lines.map((line, index) => (
                <DependencyArrow key={`${line.fromId}-${line.toId}-${index}`} line={line} />
              ))}
            </svg>

            {/* ノード層 */}
            <div
              className="relative"
              style={{
                width: viewportSize.width,
                height: viewportSize.height,
              }}
            >
              {nodes.map(node => (
                <TaskNodeComponent
                  key={node.task.id}
                  node={node}
                  onClick={() => handleTaskClick(node.task)}
                  stepInfo={stepInfoMap.get(node.task.id)}
                />
              ))}
            </div>
          </div>

          {/* 凡例 */}
          <div className="px-4 py-3 border-t border-gray-200 bg-gray-50">
            <div className="flex flex-wrap gap-3 justify-center text-xs">
              {(['QUEUED', 'BLOCKED', 'IN_PROGRESS', 'REWORK', 'DONE', 'IN_REVIEW', 'COMPLETED', 'CANCELLED', 'REJECTED', 'SKIPPED'] as const).map((status) => {
                const colors = statusColors[status];
                if (!colors) return null;
                return (
                  <div key={status} className="flex items-center space-x-1">
                    <StatusIcon status={status} className={`w-3 h-3 ${colors.text}`} />
                    <div className={`w-3 h-3 rounded border ${colors.bg} ${colors.border}`} />
                    <span className="text-gray-600">{status}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
      {/* ORDER_135 TASK_1152: TaskDetailPanelはLayoutに集約したため削除 */}
    </div>
  );
};
