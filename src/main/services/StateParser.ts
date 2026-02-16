/**
 * STATE.md Parser Service
 *
 * STATE.mdファイルをパースしてプロジェクト状態を取得するサービス
 * 各セクション（プロジェクト情報、タスク一覧、レビューキュー、進捗サマリ）を解析
 */

import * as fs from 'fs';
import * as path from 'path';

/**
 * プロジェクト情報
 */
export interface ProjectInfo {
  name: string;
  status: string;
  activeOrderCount: number;
  currentOrderId?: string;
  startDate?: string;
  targetCompletionDate?: string;
}

/**
 * タスク情報
 */
export interface TaskInfo {
  id: string;
  title: string;
  status: string;
  assignee: string;
  dependencies: string[];
  startDate?: string;
  completedDate?: string;
}

/**
 * レビューキューアイテム
 */
export interface ReviewQueueItem {
  taskId: string;
  submittedAt: string;
  status: string;
  reviewer?: string;
  priority: string;
  note?: string;
}

/**
 * 進捗サマリ
 */
export interface ProgressSummary {
  completed: number;
  inProgress: number;
  reviewWaiting: number;
  queued: number;
  blocked: number;
  rework: number;
  total: number;
}

/**
 * パース結果
 */
export interface ParsedState {
  projectInfo: ProjectInfo;
  tasks: TaskInfo[];
  reviewQueue: ReviewQueueItem[];
  progressSummary: ProgressSummary;
  orders: OrderInfo[];
}

/**
 * ORDER情報
 */
export interface OrderInfo {
  id: string;
  title?: string;
  status: string;
  tasks: TaskInfo[];
}

/**
 * パースエラー
 */
export class StateParseError extends Error {
  constructor(
    public readonly section: string,
    message: string,
    public readonly line?: number
  ) {
    super(`[${section}] ${message}${line ? ` (line ${line})` : ''}`);
    this.name = 'StateParseError';
  }
}

/**
 * StateParser
 */
export class StateParser {
  /**
   * STATE.mdファイルをパースする
   */
  parseFile(filePath: string): ParsedState {
    if (!fs.existsSync(filePath)) {
      throw new StateParseError('file', `File not found: ${filePath}`);
    }

    const content = fs.readFileSync(filePath, 'utf-8');
    return this.parse(content);
  }

  /**
   * STATE.md文字列をパースする
   */
  parse(content: string): ParsedState {
    const lines = content.split('\n');

    const projectInfo = this.parseProjectInfo(lines);
    const { orders, tasks } = this.parseTaskSections(lines);
    const reviewQueue = this.parseReviewQueue(lines);
    const progressSummary = this.parseProgressSummary(lines, tasks);

    return {
      projectInfo,
      tasks,
      reviewQueue,
      progressSummary,
      orders,
    };
  }

  /**
   * プロジェクト情報セクションをパース
   */
  private parseProjectInfo(lines: string[]): ProjectInfo {
    const info: ProjectInfo = {
      name: '',
      status: 'INITIAL',
      activeOrderCount: 0,
    };

    let inSection = false;

    for (const line of lines) {
      // セクション検出
      if (line.match(/^##\s*プロジェクト情報/)) {
        inSection = true;
        continue;
      }

      // 次のセクション開始で終了
      if (inSection && line.match(/^##\s+[^#]/)) {
        break;
      }

      if (!inSection) continue;

      // プロジェクト名のパース
      const nameMatch = line.match(/\*\*プロジェクト名\*\*:\s*(.+)/);
      if (nameMatch) {
        info.name = nameMatch[1].trim();
        continue;
      }

      // ステータスのパース
      const statusMatch = line.match(/\*\*現在ステータス\*\*:\s*`?([A-Z_]+)`?/);
      if (statusMatch) {
        info.status = statusMatch[1];
        continue;
      }

      // アクティブORDER数のパース
      const activeMatch = line.match(/\*\*アクティブORDER数\*\*:\s*(\d+)/);
      if (activeMatch) {
        info.activeOrderCount = parseInt(activeMatch[1], 10);
        continue;
      }

      // アクティブORDERのパース
      const currentOrderMatch = line.match(/\*\*アクティブORDER\*\*:\s*(ORDER_\d+)/);
      if (currentOrderMatch) {
        info.currentOrderId = currentOrderMatch[1];
        continue;
      }

      // 発注ID（アクティブORDERがない場合の代替）
      const orderIdMatch = line.match(/\*\*発注ID\*\*:\s*(ORDER_\d+)/);
      if (orderIdMatch && !info.currentOrderId) {
        info.currentOrderId = orderIdMatch[1];
        continue;
      }

      // 開始日のパース
      const startDateMatch = line.match(/\*\*開始日\*\*:\s*(\d{4}-\d{2}-\d{2})/);
      if (startDateMatch) {
        info.startDate = startDateMatch[1];
        continue;
      }

      // 目標完了日のパース
      const targetDateMatch = line.match(/\*\*目標完了日\*\*:\s*(\d{4}-\d{2}-\d{2}|-)/);
      if (targetDateMatch && targetDateMatch[1] !== '-') {
        info.targetCompletionDate = targetDateMatch[1];
        continue;
      }
    }

    return info;
  }

  /**
   * タスク一覧セクションをパース
   * 複数のORDERセクションに対応
   */
  private parseTaskSections(lines: string[]): { orders: OrderInfo[], tasks: TaskInfo[] } {
    const orders: OrderInfo[] = [];
    const allTasks: TaskInfo[] = [];

    let currentOrder: OrderInfo | null = null;
    let inTable = false;
    let headerParsed = false;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      // ORDER セクション開始を検出
      const orderMatch = line.match(/^##\s*タスク一覧（(ORDER_\d+)）(?:【(.+)】)?/);
      if (orderMatch) {
        // 前のORDERを保存
        if (currentOrder) {
          orders.push(currentOrder);
        }

        currentOrder = {
          id: orderMatch[1],
          status: orderMatch[2] || 'IN_PROGRESS',
          tasks: [],
        };
        inTable = false;
        headerParsed = false;
        continue;
      }

      // ORDER目的（title）を検出: "> **目的**: ..." の形式
      if (currentOrder && !currentOrder.title) {
        const titleMatch = line.match(/^>\s*\*\*目的\*\*:\s*(.+)/);
        if (titleMatch) {
          currentOrder.title = titleMatch[1].trim();
          continue;
        }
      }

      // タスク一覧セクション開始（ORDER指定なし）
      const taskSectionMatch = line.match(/^##\s*タスク一覧/);
      if (taskSectionMatch && !line.includes('（')) {
        if (currentOrder) {
          orders.push(currentOrder);
        }
        currentOrder = {
          id: 'UNKNOWN',
          status: 'IN_PROGRESS',
          tasks: [],
        };
        inTable = false;
        headerParsed = false;
        continue;
      }

      // 次のメインセクション開始で終了
      if (currentOrder && line.match(/^##\s+[^#]/) && !line.includes('タスク一覧')) {
        if (!line.match(/^###/)) {
          orders.push(currentOrder);
          currentOrder = null;
          inTable = false;
        }
        continue;
      }

      if (!currentOrder) continue;

      // テーブルヘッダー検出
      if (line.includes('| Task ID') || line.includes('|Task ID')) {
        inTable = true;
        headerParsed = false;
        continue;
      }

      // テーブル区切り行をスキップ
      if (line.match(/^\|[\s\-:]+\|/)) {
        headerParsed = true;
        continue;
      }

      // テーブル行のパース
      if (inTable && headerParsed && line.startsWith('|')) {
        const task = this.parseTaskRow(line);
        if (task) {
          currentOrder.tasks.push(task);
          allTasks.push(task);
        }
        continue;
      }

      // テーブル終了検出
      if (inTable && !line.startsWith('|') && line.trim() !== '') {
        inTable = false;
      }
    }

    // 最後のORDERを保存
    if (currentOrder) {
      orders.push(currentOrder);
    }

    return { orders, tasks: allTasks };
  }

  /**
   * タスク行をパース
   */
  private parseTaskRow(line: string): TaskInfo | null {
    // パイプで分割して各セルを取得
    const cells = line.split('|')
      .map(cell => cell.trim())
      .filter(cell => cell !== '');

    if (cells.length < 4) return null;

    // Task IDがない行（ヘッダーや空行）をスキップ
    const taskIdMatch = cells[0].match(/TASK_\d+(?:_INT(?:_\d+)?)?/);
    if (!taskIdMatch) return null;

    const dependencies = cells[4] && cells[4] !== '-'
      ? cells[4].split(',').map(d => d.trim()).filter(d => d)
      : [];

    return {
      id: cells[0],
      title: cells[1] || '',
      status: cells[2] || 'QUEUED',
      assignee: cells[3] || '-',
      dependencies,
      startDate: cells[5] && cells[5] !== '-' ? cells[5] : undefined,
      completedDate: cells[6] && cells[6] !== '-' ? cells[6] : undefined,
    };
  }

  /**
   * レビューキューセクションをパース
   */
  private parseReviewQueue(lines: string[]): ReviewQueueItem[] {
    const queue: ReviewQueueItem[] = [];
    let inSection = false;
    let inTable = false;
    let headerParsed = false;

    for (const line of lines) {
      // セクション検出
      if (line.match(/^##\s*レビューキュー/)) {
        inSection = true;
        continue;
      }

      // 次のセクション開始で終了
      if (inSection && line.match(/^##\s+[^#]/) && !line.match(/^###/)) {
        break;
      }

      if (!inSection) continue;

      // テーブルヘッダー検出
      if (line.includes('| Task ID') || line.includes('|Task ID')) {
        inTable = true;
        headerParsed = false;
        continue;
      }

      // テーブル区切り行をスキップ
      if (line.match(/^\|[\s\-:]+\|/)) {
        headerParsed = true;
        continue;
      }

      // テーブル行のパース
      if (inTable && headerParsed && line.startsWith('|')) {
        const item = this.parseReviewQueueRow(line);
        if (item) {
          queue.push(item);
        }
        continue;
      }

      // テーブル終了検出
      if (inTable && !line.startsWith('|') && line.trim() !== '') {
        inTable = false;
      }
    }

    return queue;
  }

  /**
   * レビューキュー行をパース
   */
  private parseReviewQueueRow(line: string): ReviewQueueItem | null {
    const cells = line.split('|')
      .map(cell => cell.trim())
      .filter(cell => cell !== '');

    if (cells.length < 5) return null;

    // Task IDがない行をスキップ
    const taskIdMatch = cells[0].match(/TASK_\d+(?:_INT(?:_\d+)?)?/);
    if (!taskIdMatch) return null;

    // "-" のみの行（空エントリ）をスキップ
    if (cells[0] === '-') return null;

    return {
      taskId: cells[0],
      submittedAt: cells[1] || '',
      status: cells[2] || 'PENDING',
      reviewer: cells[3] && cells[3] !== '-' ? cells[3] : undefined,
      priority: cells[4] || 'P1',
      note: cells[5] && cells[5] !== '-' ? cells[5] : undefined,
    };
  }

  /**
   * 進捗サマリセクションをパース
   */
  private parseProgressSummary(lines: string[], tasks: TaskInfo[]): ProgressSummary {
    const summary: ProgressSummary = {
      completed: 0,
      inProgress: 0,
      reviewWaiting: 0,
      queued: 0,
      blocked: 0,
      rework: 0,
      total: tasks.length,
    };

    let inSection = false;

    for (const line of lines) {
      // セクション検出
      if (line.match(/^##\s*進捗サマリ/)) {
        inSection = true;
        continue;
      }

      // 次のセクション開始で終了
      if (inSection && line.match(/^##\s+[^#]/) && !line.match(/^###/)) {
        break;
      }

      if (!inSection) continue;

      // 完了タスク数
      const completedMatch = line.match(/\*\*完了タスク数\*\*:\s*(\d+)/);
      if (completedMatch) {
        summary.completed = parseInt(completedMatch[1], 10);
        continue;
      }

      // 進行中タスク数
      const inProgressMatch = line.match(/\*\*進行中タスク数\*\*:\s*(\d+)/);
      if (inProgressMatch) {
        summary.inProgress = parseInt(inProgressMatch[1], 10);
        continue;
      }

      // レビュー待ちタスク数
      const reviewMatch = line.match(/\*\*レビュー待ちタスク数\*\*:\s*(\d+)/);
      if (reviewMatch) {
        summary.reviewWaiting = parseInt(reviewMatch[1], 10);
        continue;
      }

      // 待機中タスク数
      const queuedMatch = line.match(/\*\*待機中タスク数\*\*:\s*(\d+)/);
      if (queuedMatch) {
        summary.queued = parseInt(queuedMatch[1], 10);
        continue;
      }

      // ブロック中タスク数
      const blockedMatch = line.match(/\*\*ブロック中タスク数\*\*:\s*(\d+)/);
      if (blockedMatch) {
        summary.blocked = parseInt(blockedMatch[1], 10);
        continue;
      }

      // 差し戻しタスク数
      const reworkMatch = line.match(/\*\*差し戻しタスク数\*\*:\s*(\d+)/);
      if (reworkMatch) {
        summary.rework = parseInt(reworkMatch[1], 10);
        continue;
      }
    }

    // 進捗サマリセクションが見つからない場合、タスク一覧から計算
    if (!inSection && tasks.length > 0) {
      summary.completed = tasks.filter(t => t.status === 'COMPLETED').length;
      summary.inProgress = tasks.filter(t => t.status === 'IN_PROGRESS').length;
      summary.reviewWaiting = tasks.filter(t => t.status === 'DONE').length;
      summary.queued = tasks.filter(t => t.status === 'QUEUED').length;
      summary.blocked = tasks.filter(t => t.status === 'BLOCKED').length;
      summary.rework = tasks.filter(t => t.status === 'REWORK').length;
    }

    return summary;
  }

  /**
   * 指定したORDERのタスク一覧を取得
   */
  parseOrderTasks(content: string, orderId: string): TaskInfo[] {
    const { orders } = this.parseTaskSections(content.split('\n'));
    const order = orders.find(o => o.id === orderId);
    return order?.tasks || [];
  }

  /**
   * ファイルが有効なSTATE.mdかどうかを検証
   */
  isValidStateFile(content: string): boolean {
    // プロジェクト情報セクションの存在チェック
    const hasProjectInfo = content.includes('## プロジェクト情報');

    // タスク一覧またはステータス定義の存在チェック
    const hasTaskList = content.includes('## タスク一覧');
    const hasStatusDef = content.includes('## ステータス定義');

    return hasProjectInfo && (hasTaskList || hasStatusDef);
  }
}
