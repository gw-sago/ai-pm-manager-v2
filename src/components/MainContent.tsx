import React, { useState, useCallback } from 'react';
import { TaskDependencyView } from './TaskDependencyView';
import { OrderDetailPanel } from './OrderDetailPanel';
import { BacklogList } from './BacklogList';
import { BacklogDetailPanel } from './BacklogDetailPanel';
import { ExecutionLog } from './ExecutionLog';
import { Settings } from './Settings';
import { SupervisorDashboard } from './SupervisorDashboard';
import { ProjectInfo } from './ProjectInfo';
import type { Project, TaskInfo, OrderInfo, BacklogItem, Supervisor, SupervisorProject } from '../preload';

/**
 * メインコンテンツのタブ種別（ORDER_040追加, ORDER_156拡張）
 */
type MainContentTab = 'backlog' | 'execution-log' | 'project-info';


/**
 * フレームワーク設定の状態
 */
type FrameworkConfigState = 'loading' | 'configured' | 'not_configured';

interface MainContentProps {
  children?: React.ReactNode;
  /** 現在選択中のプロジェクト（Layout.tsxから渡される） */
  selectedProject?: Project | null;
  /** 現在選択中のORDER（Layout.tsxから渡される） */
  selectedOrder?: OrderInfo | null;
  /** フレームワーク設定の状態（Layout.tsxから渡される） */
  frameworkConfigState?: FrameworkConfigState;
  /** 設定画面が表示中かどうか（Layout.tsxから渡される） */
  isSettingsOpen?: boolean;
  /** 設定画面を閉じるコールバック */
  onSettingsClose?: () => void;
  /** フレームワークパス変更時のコールバック */
  onFrameworkPathChange?: (newPath: string) => void;
  /** バックログ項目クリック時のコールバック（ORDER_038追加） */
  onBacklogItemClick?: (item: BacklogItem) => void;
  /** ORDER IDクリック時のコールバック */
  onOrderIdClick?: (orderId: string) => void;
  /** 選択中のSupervisor（ORDER_060追加） */
  selectedSupervisor?: Supervisor | null;
  /** SupervisorDashboardからプロジェクト選択時のコールバック（ORDER_060追加） */
  onSupervisorProjectSelect?: (project: SupervisorProject) => void;
  /** ORDER_135 TASK_1152: タスク詳細パネル表示時のコールバック（Layoutから渡される） */
  onTaskDetailPanelOpen?: (taskId: string) => void;
}

export const MainContent: React.FC<MainContentProps> = ({
  children,
  selectedProject,
  selectedOrder,
  frameworkConfigState = 'loading',
  isSettingsOpen = false,
  onSettingsClose,
  onFrameworkPathChange,
  onBacklogItemClick,
  onOrderIdClick,
  selectedSupervisor,
  onSupervisorProjectSelect,
  onTaskDetailPanelOpen,
}) => {
  return (
    <main className="flex-1 bg-gray-50 overflow-auto">
      <div className="p-4 h-full">
        {/* 設定画面が開いている場合 */}
        {isSettingsOpen ? (
          <Settings onClose={onSettingsClose} onPathChange={onFrameworkPathChange} />
        ) : selectedSupervisor ? (
          /* Supervisor選択時は統括ダッシュボードを表示（ORDER_060追加） */
          <SupervisorDashboard
            supervisor={selectedSupervisor}
            onProjectSelect={onSupervisorProjectSelect}
          />
        ) : (
          children || (
            <DefaultContent
              selectedProject={selectedProject}
              selectedOrder={selectedOrder}
              frameworkConfigState={frameworkConfigState}
              onBacklogItemClick={onBacklogItemClick}
              onOrderIdClick={onOrderIdClick}
              onTaskDetailPanelOpen={onTaskDetailPanelOpen}
            />
          )
        )}
      </div>
    </main>
  );
};

interface DefaultContentProps {
  /** Layout.tsxから渡されるプロジェクト選択状態 */
  selectedProject?: Project | null;
  /** Layout.tsxから渡されるORDER選択状態 */
  selectedOrder?: OrderInfo | null;
  /** フレームワーク設定の状態（Layout.tsxから渡される） */
  frameworkConfigState?: FrameworkConfigState;
  /** バックログ項目クリック時のコールバック（ORDER_038追加） */
  onBacklogItemClick?: (item: BacklogItem) => void;
  /** ORDER IDクリック時のコールバック */
  onOrderIdClick?: (orderId: string) => void;
  /** ORDER_135 TASK_1152: タスク詳細パネル表示時のコールバック（Layoutから渡される） */
  onTaskDetailPanelOpen?: (taskId: string) => void;
}

const DefaultContent: React.FC<DefaultContentProps> = ({
  selectedProject,
  selectedOrder,
  frameworkConfigState = 'loading',
  onBacklogItemClick,
  onOrderIdClick,
  onTaskDetailPanelOpen,
}) => {
  const [selectedBacklogItem, setSelectedBacklogItem] = useState<BacklogItem | null>(null);
  // タブ切り替え状態（ORDER_040追加）
  const [activeTab, setActiveTab] = useState<MainContentTab>('backlog');

  // フレームワークが設定済みかどうか
  const isFrameworkConfigured = frameworkConfigState === 'configured';

  /**
   * バックログ項目クリックハンドラ（ORDER_123 TASK_1108追加）
   */
  const handleBacklogItemClick = useCallback((item: BacklogItem) => {
    console.log('[MainContent] Backlog item clicked:', {
      id: item.id,
      title: item.title,
      projectId: item.projectId,
    });
    setSelectedBacklogItem(item);
    // 親コンポーネントのコールバックも呼び出し（互換性維持）
    onBacklogItemClick?.(item);
  }, [onBacklogItemClick]);

  /**
   * バックログ詳細を閉じるハンドラ（ORDER_123 TASK_1108追加）
   */
  const handleBacklogDetailClose = useCallback(() => {
    setSelectedBacklogItem(null);
  }, []);

  /**
   * バックログ詳細からORDER IDクリック時のハンドラ（ORDER_123 TASK_1108追加）
   */
  const handleBacklogOrderClick = useCallback((orderId: string) => {
    console.log('[MainContent] Order clicked from backlog detail:', orderId);
    // バックログ詳細を閉じる
    setSelectedBacklogItem(null);
    // 親コンポーネントのORDERクリックコールバックを呼び出し
    onOrderIdClick?.(orderId);
  }, [onOrderIdClick]);

  /**
   * ORDER詳細パネルを閉じるハンドラ（互換性維持）
   */
  const handleOrderDetailClose = useCallback(() => {
    // ORDER詳細パネルは常時表示のため、閉じる動作は行わない
  }, []);

  // ローディング中の表示
  if (frameworkConfigState === 'loading') {
    return (
      <div className="flex flex-col min-h-[calc(100vh-12rem)] items-center justify-center">
        <div className="flex flex-col items-center text-gray-500">
          <svg
            className="animate-spin h-8 w-8 mb-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span className="text-sm">設定を読み込み中...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-[calc(100vh-12rem)]">
      {/* 未設定時：設定画面への誘導メッセージ */}
      {!isFrameworkConfigured && (
        <div className="flex flex-col h-full items-center justify-center">
          <div className="text-center max-w-md">
            {/* アイコン */}
            <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 rounded-full mb-6">
              <svg
                className="w-8 h-8 text-blue-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
            </div>

            {/* メッセージ */}
            <h2 className="text-xl font-semibold text-gray-800 mb-2">
              フレームワーク設定が必要です
            </h2>
            <p className="text-sm text-gray-500 mb-6">
              プロジェクト管理を開始するには、サイドバーの「設定」から
              AI PM Frameworkのディレクトリを設定してください。
            </p>

            {/* ヒント */}
            <div className="bg-gray-50 rounded-lg p-4 text-left">
              <div className="flex items-start">
                <svg
                  className="w-5 h-5 text-gray-400 mt-0.5 mr-3 flex-shrink-0"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                <div>
                  <p className="text-xs text-gray-500">
                    AI PM Frameworkのルートディレクトリ（PROJECTS/フォルダを含むディレクトリ）を
                    選択すると、プロジェクト一覧が表示されます。
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* フレームワーク設定済みコンテンツ */}
      {isFrameworkConfigured && (
        <div className="flex flex-col h-full space-y-4">
          {/* タブ切り替えUI（ORDER_040追加, ORDER_156拡張） */}
          {selectedProject && selectedProject.state && (
            <div className="flex border-b border-gray-200">
              <button
                onClick={() => setActiveTab('backlog')}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'backlog'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                バックログ
              </button>
              <button
                onClick={() => setActiveTab('execution-log')}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'execution-log'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                実行ログ
              </button>
              <button
                onClick={() => setActiveTab('project-info')}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === 'project-info'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                プロジェクト情報
              </button>
            </div>
          )}

          {/* バックログ一覧（プロジェクト選択時 & バックログタブ選択時） */}
          {selectedProject && selectedProject.state && activeTab === 'backlog' && (
            <div className="w-full">
              <BacklogList
                projectName={selectedProject.name}
                showFilterBar={true}
                compactFilterBar={true}
                maxItems={10}
                title="バックログ一覧"
                initialFilters={{ status: ['TODO', 'IN_PROGRESS'], sortBy: 'priority', sortOrder: 'desc' }}
                onItemClick={handleBacklogItemClick}
                onOrderClick={onOrderIdClick}
              />
            </div>
          )}

          {/* 実行ログ（プロジェクト選択時 & 実行ログタブ選択時）（ORDER_040追加, ORDER_059でサブタブ削除） */}
          {selectedProject && selectedProject.state && activeTab === 'execution-log' && (
            <div className="w-full">
              <ExecutionLog maxItems={50} projectId={selectedProject.name} />
            </div>
          )}

          {/* プロジェクト情報（プロジェクト選択時 & プロジェクト情報タブ選択時）（ORDER_156 / TASK_1233） */}
          {selectedProject && selectedProject.state && activeTab === 'project-info' && (
            <div className="w-full">
              <ProjectInfo projectId={selectedProject.name} />
            </div>
          )}

          {/* プロジェクト未選択時のメッセージ */}
          {!selectedProject && (
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="text-center py-8">
                <div className="inline-flex items-center justify-center w-12 h-12 bg-blue-100 rounded-full mb-4">
                  <svg
                    className="w-6 h-6 text-blue-500"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122"
                    />
                  </svg>
                </div>
                <h3 className="text-sm font-medium text-gray-900 mb-1">
                  プロジェクトを選択してください
                </h3>
                <p className="text-xs text-gray-500">
                  サイドバーからプロジェクトを選択すると、バックログ一覧が表示されます
                </p>
              </div>
            </div>
          )}

          {/* メイン: 依存関係ビュー + ORDER詳細パネル（ORDER選択時） */}
          {selectedOrder && selectedProject && (
            <div className="flex-1 min-h-0 flex flex-col space-y-4">
              {/* 依存関係ビュー（常時表示・折りたたみ可能） */}
              <TaskDependencyView
                order={selectedOrder}
                onTaskClick={(task: TaskInfo) => onTaskDetailPanelOpen?.(task.id)}
                collapsible={true}
                defaultExpanded={true}
                projectId={selectedProject.name}
              />

              {/* ORDER詳細パネル */}
              <div className="flex-1 min-h-0">
                <OrderDetailPanel
                  projectName={selectedProject.name}
                  order={selectedOrder}
                  onClose={handleOrderDetailClose}
                  onTaskClick={onTaskDetailPanelOpen}
                />
              </div>
            </div>
          )}

          {/* ORDER未選択時のプレースホルダー */}
          {selectedProject && !selectedOrder && (
            <div className="flex-1 bg-white rounded-lg shadow-sm border border-gray-200 p-6">
              <div className="flex flex-col items-center justify-center h-full text-center">
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
                      d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                    />
                  </svg>
                </div>
                <h3 className="text-sm font-medium text-gray-900 mb-1">
                  ORDERを選択してください
                </h3>
                <p className="text-xs text-gray-500">
                  サイドバーからORDERを選択すると、タスク依存関係が表示されます
                </p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ORDER_135 TASK_1152: TaskDetailPanelはLayoutに集約したため削除 */}

      {/* バックログ詳細モーダル（ORDER_123 TASK_1108追加） */}
      {selectedBacklogItem && (
        <BacklogDetailPanel
          item={selectedBacklogItem}
          onClose={handleBacklogDetailClose}
          onOrderClick={handleBacklogOrderClick}
        />
      )}
    </div>
  );
};
