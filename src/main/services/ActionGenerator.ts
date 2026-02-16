/**
 * ActionGenerator - 推奨アクション生成サービス
 *
 * プロジェクト状態から推奨コマンド（次のアクション）を自動生成するサービス
 *
 * TASK_025: 推奨アクション生成ロジック実装
 */

import type { ParsedState, TaskInfo, ReviewQueueItem } from './StateParser';

/**
 * 推奨アクションの種類
 */
export type ActionType = 'review' | 'worker' | 'status';

/**
 * 推奨アクション
 */
export interface RecommendedAction {
  /** 一意識別子 */
  id: string;
  /** アクションタイプ */
  type: ActionType;
  /** 実行コマンド */
  command: string;
  /** 説明テキスト */
  description: string;
  /** 優先度（0が最優先） */
  priority: number;
  /** 関連タスクID（オプション） */
  taskId?: string;
}

/**
 * アクション生成オプション
 */
export interface ActionGeneratorOptions {
  /** 最大生成件数（デフォルト: 3） */
  maxActions?: number;
}

/**
 * ActionGenerator クラス
 *
 * プロジェクト状態を分析し、推奨アクションを生成する
 */
export class ActionGenerator {
  private readonly maxActions: number;

  constructor(options: ActionGeneratorOptions = {}) {
    this.maxActions = options.maxActions ?? 3;
  }

  /**
   * プロジェクト状態から推奨アクションを生成
   *
   * @param projectName プロジェクト名
   * @param state パース済みのプロジェクト状態
   * @returns 推奨アクションの配列（優先度順、最大maxActions件）
   */
  generate(projectName: string, state: ParsedState): RecommendedAction[] {
    const actions: RecommendedAction[] = [];

    // 0. IN_PROGRESSタスクを検出（優先度0: 再実行が必要）
    // ORDER_100 TASK_967: 中断タスクの再実行UI
    const inProgressActions = this.generateInProgressActions(projectName, state.tasks);
    actions.push(...inProgressActions);

    // 1. REWORKタスクを検出（優先度1: 最優先）
    const reworkActions = this.generateReworkActions(projectName, state.tasks);
    actions.push(...reworkActions);

    // 2. レビュー待ちを検出（優先度2）
    const reviewActions = this.generateReviewActions(projectName, state.tasks, state.reviewQueue);
    actions.push(...reviewActions);

    // 3. 実行可能タスク（QUEUED）を検出（優先度3）
    const queuedActions = this.generateQueuedActions(projectName, state.tasks);
    actions.push(...queuedActions);

    // 4. 全タスク完了の場合（優先度5）
    if (actions.length === 0) {
      const statusAction = this.generateStatusAction(projectName, state);
      if (statusAction) {
        actions.push(statusAction);
      }
    }

    // 優先度順にソート
    actions.sort((a, b) => a.priority - b.priority);

    // 最大件数に制限
    return actions.slice(0, this.maxActions);
  }

  /**
   * IN_PROGRESSタスクに対する再実行アクションを生成
   * 優先度0（再実行が必要 - 最優先）
   * ORDER_100 TASK_967: 中断タスクの再実行UI実装
   */
  private generateInProgressActions(projectName: string, tasks: TaskInfo[]): RecommendedAction[] {
    const inProgressTasks = tasks.filter(t => t.status === 'IN_PROGRESS');

    return inProgressTasks.map((task, index) => ({
      id: `retry-${task.id}-${index}`,
      type: 'worker' as ActionType,
      command: `/aipm-worker ${projectName} ${task.id.replace('TASK_', '')}`,
      description: `中断タスクを再実行: ${task.title}`,
      priority: 0,
      taskId: task.id,
    }));
  }

  /**
   * REWORKタスクに対するアクションを生成
   * 優先度1（最優先）
   */
  private generateReworkActions(projectName: string, tasks: TaskInfo[]): RecommendedAction[] {
    const reworkTasks = tasks.filter(t => t.status === 'REWORK');

    return reworkTasks.map((task, index) => ({
      id: `rework-${task.id}-${index}`,
      type: 'worker' as ActionType,
      command: `/aipm-worker ${projectName} ${task.id.replace('TASK_', '')}`,
      description: `差し戻しタスクを修正: ${task.title}`,
      priority: 1,
      taskId: task.id,
    }));
  }

  /**
   * レビュー待ちタスクに対するアクションを生成
   * 優先度2
   *
   * DONEステータスのタスク、またはレビューキューのPENDINGを検出
   */
  private generateReviewActions(
    projectName: string,
    tasks: TaskInfo[],
    reviewQueue: ReviewQueueItem[]
  ): RecommendedAction[] {
    const actions: RecommendedAction[] = [];

    // DONEステータスのタスクを検出
    const doneTasks = tasks.filter(t => t.status === 'DONE');

    // レビューキューのPENDINGエントリを検出
    const pendingReviews = reviewQueue.filter(r => r.status === 'PENDING');

    // レビュー待ちがある場合
    if (doneTasks.length > 0 || pendingReviews.length > 0) {
      // 一般的なレビュー実行コマンド
      actions.push({
        id: 'review-next',
        type: 'review' as ActionType,
        command: `/aipm-review ${projectName} --next`,
        description: `レビュー待ちタスクをレビュー（${Math.max(doneTasks.length, pendingReviews.length)}件）`,
        priority: 2,
      });

      // 個別のレビュー待ちタスク（優先度が高いものから）
      // P0 > P1 > P2の順でソート
      const sortedPending = [...pendingReviews].sort((a, b) => {
        const priorityA = this.parsePriority(a.priority);
        const priorityB = this.parsePriority(b.priority);
        return priorityA - priorityB;
      });

      // 最優先のレビューがあれば個別アクションも追加
      if (sortedPending.length > 0 && sortedPending[0].priority === 'P0') {
        const p0Review = sortedPending[0];
        const taskNumber = p0Review.taskId.replace('TASK_', '');
        actions.push({
          id: `review-${p0Review.taskId}`,
          type: 'review' as ActionType,
          command: `/aipm-review ${projectName} ${taskNumber}`,
          description: `優先レビュー（P0）: ${p0Review.taskId}`,
          priority: 2,
          taskId: p0Review.taskId,
        });
      }
    }

    return actions;
  }

  /**
   * QUEUEDタスクに対するアクションを生成
   * 優先度3
   */
  private generateQueuedActions(projectName: string, tasks: TaskInfo[]): RecommendedAction[] {
    const queuedTasks = tasks.filter(t => t.status === 'QUEUED');

    return queuedTasks.map((task, index) => ({
      id: `queued-${task.id}-${index}`,
      type: 'worker' as ActionType,
      command: `/aipm-worker ${projectName} ${task.id.replace('TASK_', '')}`,
      description: `次のタスクを開始: ${task.title}`,
      priority: 3,
      taskId: task.id,
    }));
  }

  /**
   * 全タスク完了時のステータス確認アクションを生成
   * 優先度5
   */
  private generateStatusAction(projectName: string, state: ParsedState): RecommendedAction | null {
    const { tasks } = state;

    // タスクがない、または全て完了している場合
    const allCompleted = tasks.length === 0 ||
      tasks.every(t => t.status === 'COMPLETED');

    if (allCompleted) {
      return {
        id: 'status-check',
        type: 'status' as ActionType,
        command: `/aipm-status ${projectName}`,
        description: '全タスク完了 - ステータス確認',
        priority: 5,
      };
    }

    return null;
  }

  /**
   * 優先度文字列を数値に変換
   * P0 -> 0, P1 -> 1, P2 -> 2, ...
   */
  private parsePriority(priority: string): number {
    const match = priority.match(/P(\d+)/);
    if (match) {
      return parseInt(match[1], 10);
    }
    return 99; // 不明な優先度は最低に
  }
}

/**
 * ActionGeneratorのシングルトンインスタンス
 */
let actionGeneratorInstance: ActionGenerator | null = null;

/**
 * ActionGeneratorのシングルトンインスタンスを取得
 */
export function getActionGenerator(): ActionGenerator {
  if (!actionGeneratorInstance) {
    actionGeneratorInstance = new ActionGenerator();
  }
  return actionGeneratorInstance;
}

/**
 * ActionGeneratorインスタンスをリセット（テスト用）
 */
export function resetActionGenerator(): void {
  actionGeneratorInstance = null;
}
