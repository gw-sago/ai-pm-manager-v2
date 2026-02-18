import React, { useState, useEffect, useCallback } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { MainContent } from './MainContent';
import { ReportViewer } from './ReportViewer';
import { FloatingProgressPanel } from './FloatingProgressPanel';
import { TaskLogModal } from './TaskLogModal';
import { TaskDetailPanel } from './TaskDetailPanel';
import type { Project, OrderInfo, TaskInfo, BacklogItem, Supervisor, SupervisorProject } from '../preload';

interface LayoutProps {
  children?: React.ReactNode;
}

/**
 * フレームワーク設定の状態
 */
type FrameworkConfigState = 'loading' | 'configured' | 'not_configured';

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<OrderInfo | null>(null);
  // ReportViewer表示用のタスク選択状態
  const [selectedTaskForReport, setSelectedTaskForReport] = useState<TaskInfo | null>(null);
  // Supervisor選択状態（ORDER_060追加）
  const [selectedSupervisor, setSelectedSupervisor] = useState<Supervisor | null>(null);

  // フレームワーク設定の状態（起動時自動読み込み対応）
  const [frameworkConfigState, setFrameworkConfigState] = useState<FrameworkConfigState>('loading');
  // const [activeFrameworkPath, setActiveFrameworkPath] = useState<string | null>(null); // ORDER_152: 未使用のため削除

  // 設定画面の表示状態（ORDER_152: 設定画面削除により常にfalse）
  // const [isSettingsOpen] = useState(false); // 未使用のため削除

  // ORDER_128: タスクログ表示用の状態
  const [taskLogViewState, setTaskLogViewState] = useState<{
    taskId: string;
    projectId: string;
    logFile?: string;
    hasError?: boolean;
  } | null>(null);

  // ORDER_135 TASK_1152: タスク詳細パネル用の選択状態（state管理をLayoutにリフトアップ）
  const [selectedTaskDetailId, setSelectedTaskDetailId] = useState<string | null>(null);

  /**
   * メニュー更新処理（ORDER_063 / TASK_677）
   * ボタン操作・自動実行完了時にプロジェクト一覧・ORDER一覧を自動更新
   */
  const refreshMenu = useCallback(async () => {
    console.log('[Layout] menu:update event received, refreshing...');

    // 選択中のプロジェクトがある場合、stateを再取得
    if (selectedProject) {
      try {
        const freshState = await window.electronAPI.getProjectState(selectedProject.name);
        if (freshState) {
          setSelectedProject((prev) =>
            prev ? { ...prev, state: freshState } : prev
          );

          // 選択中のORDERも更新
          if (selectedOrder && freshState.orders) {
            const freshOrder = freshState.orders.find((o: OrderInfo) => o.id === selectedOrder.id);
            if (freshOrder) {
              setSelectedOrder(freshOrder);
            }
          }
          console.log('[Layout] Project state refreshed for:', selectedProject.name);
        }
      } catch (error) {
        console.error('[Layout] Failed to refresh project state:', error);
      }
    }
  }, [selectedProject, selectedOrder]);

  // メニュー更新イベントをリッスン（ORDER_063 / TASK_677）
  useEffect(() => {
    const unsubscribe = window.electronAPI.onMenuUpdate(() => {
      refreshMenu();
    });

    return () => {
      unsubscribe();
    };
  }, [refreshMenu]);

  // ORDER_128: FloatingProgressPanelからのタスクログ表示イベントをリッスン
  useEffect(() => {
    const handleOpenTaskLog = (event: CustomEvent) => {
      const { taskId, projectId, logFile, hasError } = event.detail;
      console.log('[Layout] open-task-log event received:', { taskId, projectId, logFile, hasError });
      setTaskLogViewState({ taskId, projectId, logFile, hasError });
    };

    window.addEventListener('open-task-log', handleOpenTaskLog as EventListener);

    return () => {
      window.removeEventListener('open-task-log', handleOpenTaskLog as EventListener);
    };
  }, []);

  // 起動時にConfigServiceから設定を自動読み込み
  useEffect(() => {
    const loadConfig = async () => {
      try {
        const savedPath = await window.electronAPI.getActiveFrameworkPath();
        console.log('[Layout] Loaded active framework path:', savedPath);

        if (savedPath) {
          // 設定済み：パスを検証
          const validation = await window.electronAPI.validateDirectory(savedPath);
          if (validation.isValid) {
            // setActiveFrameworkPath(savedPath); // ORDER_152: 未使用のため削除
            setFrameworkConfigState('configured');
            console.log('[Layout] Framework configured and valid:', savedPath);

            // ファイル監視を開始
            const watchResult = await window.electronAPI.startWatcher(savedPath);
            if (watchResult.success) {
              console.log('[Layout] File watcher started for:', savedPath);
            }
          } else {
            // パスが無効になっている場合
            console.warn('[Layout] Saved framework path is no longer valid:', savedPath);
            setFrameworkConfigState('not_configured');
          }
        } else {
          // 未設定
          setFrameworkConfigState('not_configured');
          console.log('[Layout] No framework path configured');
        }
      } catch (error) {
        console.error('[Layout] Failed to load config:', error);
        setFrameworkConfigState('not_configured');
      }
    };

    loadConfig();
  }, []);

  const handleToggleSidebar = () => {
    setSidebarCollapsed(!sidebarCollapsed);
  };

  /**
   * サイドバーからのSupervisor選択時のハンドラ（ORDER_060追加）
   */
  const handleSupervisorSelect = useCallback((supervisor: Supervisor) => {
    setSelectedSupervisor(supervisor);
    setSelectedProject(null);
    setSelectedOrder(null);
    console.log('[Layout] Supervisor selected:', supervisor.id, supervisor.name);
  }, []);

  /**
   * SupervisorDashboardからプロジェクトが選択された時のハンドラ
   */
  const handleSupervisorProjectSelect = useCallback(async (supervisorProject: SupervisorProject) => {
    console.log('[Layout] Project selected from supervisor dashboard:', supervisorProject.id);
    // SupervisorProjectをProject形式に変換
    const project: Project = {
      name: supervisorProject.id,
      path: supervisorProject.path,
      hasStateFile: true,
      state: null,
      lastUpdated: new Date(),
    };
    // stateを取得
    try {
      const state = await window.electronAPI.getProjectState(supervisorProject.id);
      project.state = state;
    } catch (error) {
      console.error('[Layout] Failed to get project state:', error);
    }
    setSelectedSupervisor(null);
    setSelectedProject(project);
    // アクティブORDERを自動選択
    if (project.state?.orders) {
      const activeOrder = project.state.orders.find((o: OrderInfo) => o.status === 'IN_PROGRESS');
      if (activeOrder) {
        setSelectedOrder(activeOrder);
      } else {
        setSelectedOrder(null);
      }
    }
  }, []);

  /**
   * サイドバーからのプロジェクト選択時のハンドラ
   * アクティブORDER（IN_PROGRESS状態）があれば自動選択
   */
  const handleProjectSelect = useCallback((project: Project) => {
    setSelectedSupervisor(null); // Supervisor選択をクリア
    setSelectedProject(project);
    console.log('[Layout] Project selected:', project.name);

    // アクティブORDERを自動選択（project.stateから取得）
    if (project.state?.orders) {
      // IN_PROGRESS状態のORDERを探す
      const activeOrder = project.state.orders.find((o: OrderInfo) => o.status === 'IN_PROGRESS');
      if (activeOrder) {
        setSelectedOrder(activeOrder);
        console.log('[Layout] Auto-selected active order:', activeOrder.id, activeOrder.title);
      } else {
        // アクティブORDERがない場合はリセット
        setSelectedOrder(null);
        console.log('[Layout] No active order found for project');
      }
    } else {
      setSelectedOrder(null);
      console.log('[Layout] No orders available for project');
    }
  }, []);

  /**
   * ORDER選択時のハンドラ
   * ORDER_054: ORDER切り替え時にプロジェクトstateを再取得して最新データを表示
   */
  const handleOrderSelect = useCallback(async (order: OrderInfo) => {
    console.log('[Layout] Order selected:', order.id);

    // 選択中のプロジェクトがある場合、stateを再取得して最新のORDER情報を取得
    if (selectedProject) {
      try {
        const freshState = await window.electronAPI.getProjectState(selectedProject.name);
        console.log('[Layout] Refreshed project state for order selection');

        if (freshState?.orders) {
          // 再取得したstateから該当ORDERを検索
          const freshOrder = freshState.orders.find((o: OrderInfo) => o.id === order.id);
          if (freshOrder) {
            // 最新のORDERデータでselectedOrderを更新
            setSelectedOrder(freshOrder);
            console.log('[Layout] Order updated with fresh data:', freshOrder.id, 'tasks:', freshOrder.tasks?.length);

            // selectedProjectのstateも更新（サイドバーのOrderTreeも最新化）
            setSelectedProject((prev) =>
              prev ? { ...prev, state: freshState } : prev
            );
            return;
          }
        }
      } catch (error) {
        console.error('[Layout] Failed to refresh state for order selection:', error);
        // エラー時はフォールバックとして元のorderを使用
      }
    }

    // state再取得できなかった場合はフォールバック
    setSelectedOrder(order);
  }, [selectedProject]);

  /**
   * サイドバーのタスククリック時のハンドラ（ORDER_152: 現在未使用）
   * ReportViewerを表示する
   */
  // const handleTaskClick = useCallback((task: TaskInfo) => {
  //   console.log('[Layout] Task clicked for report:', task.id);
  //   setSelectedTaskForReport(task);
  // }, []);

  /**
   * ReportViewerを閉じるハンドラ
   */
  const handleReportViewerClose = useCallback(() => {
    setSelectedTaskForReport(null);
  }, []);

  /**
   * ORDER_128: タスクログモーダルを閉じるハンドラ
   */
  const handleTaskLogClose = useCallback(() => {
    setTaskLogViewState(null);
  }, []);

  /**
   * ORDER_135 TASK_1152: タスク詳細パネル表示ハンドラ（タスクIDベース）
   */
  const handleTaskDetailPanelOpen = useCallback((taskId: string) => {
    console.log('[Layout] TaskDetailPanel open:', taskId);
    setSelectedTaskDetailId(taskId);
  }, []);

  /**
   * ORDER_135 TASK_1152: タスク詳細パネルを閉じるハンドラ
   */
  const handleTaskDetailPanelClose = useCallback(() => {
    setSelectedTaskDetailId(null);
  }, []);

  /**
   * ORDER_135 TASK_1152: タスク詳細パネル内での他タスクへの遷移ハンドラ
   */
  const handleTaskDetailPanelTaskClick = useCallback((taskId: string) => {
    console.log('[Layout] TaskDetailPanel navigate to:', taskId);
    setSelectedTaskDetailId(taskId);
  }, []);

  /**
   * バックログ項目クリック時のハンドラ（ORDER_038追加）
   * 関連ORDERがある場合、そのORDERを選択状態にする
   */
  const handleBacklogItemClick = useCallback((item: BacklogItem) => {
    console.log('[Layout] Backlog item clicked:', item.id, item.relatedOrderId);

    // 関連ORDERがない場合は何もしない
    if (!item.relatedOrderId) {
      console.log('[Layout] No related order for backlog item');
      return;
    }

    // 現在選択中のプロジェクトのORDER一覧から該当ORDERを検索
    if (selectedProject?.state?.orders) {
      const targetOrder = selectedProject.state.orders.find(
        (o: OrderInfo) => o.id === item.relatedOrderId
      );
      if (targetOrder) {
        setSelectedOrder(targetOrder);
        console.log('[Layout] Selected order from backlog:', targetOrder.id, targetOrder.title);
      } else {
        console.warn('[Layout] Related order not found in project orders:', item.relatedOrderId);
      }
    }
  }, [selectedProject]);

  /**
   * ORDER IDクリック時のハンドラ
   * バックログ一覧からORDER IDがクリックされた場合、そのORDERを選択状態にする
   */
  const handleOrderIdClick = useCallback((orderId: string) => {
    console.log('[Layout] Order ID clicked:', orderId);

    // 現在選択中のプロジェクトのORDER一覧から該当ORDERを検索
    if (selectedProject?.state?.orders) {
      const targetOrder = selectedProject.state.orders.find(
        (o: OrderInfo) => o.id === orderId
      );
      if (targetOrder) {
        setSelectedOrder(targetOrder);
        console.log('[Layout] Selected order from order ID click:', targetOrder.id, targetOrder.title);
      } else {
        console.warn('[Layout] Order not found in project orders:', orderId);
        // DBにあるがファイルがない場合のために、仮のOrderInfoを作成
        // 最低限の情報で選択状態にする
        const fallbackOrder: OrderInfo = {
          id: orderId,
          title: `${orderId}`,
          status: 'COMPLETED',
          tasks: [],
        };
        setSelectedOrder(fallbackOrder);
        console.log('[Layout] Created fallback order for:', orderId);
      }
    }
  }, [selectedProject]);

  /**
   * フレームワーク設定完了時のコールバック（ORDER_152: 現在未使用）
   * MainContentから呼び出される
   */
  // const handleFrameworkConfigured = (path: string) => {
  //   setActiveFrameworkPath(path);
  //   setFrameworkConfigState('configured');
  //   console.log('[Layout] Framework configuration completed:', path);
  // };

  return (
    <div className="h-screen flex flex-col bg-gray-100">
      <Header />

      {/* Main area with sidebar */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar */}
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={handleToggleSidebar}
          selectedProject={selectedProject}
          onProjectSelect={handleProjectSelect}
          selectedOrderId={selectedOrder?.id}
          onOrderSelect={handleOrderSelect}
          selectedSupervisor={selectedSupervisor}
          onSupervisorSelect={handleSupervisorSelect}
        />

        {/* Main content */}
        <MainContent
          selectedProject={selectedProject}
          selectedOrder={selectedOrder}
          frameworkConfigState={frameworkConfigState}
          onBacklogItemClick={handleBacklogItemClick}
          onOrderIdClick={handleOrderIdClick}
          selectedSupervisor={selectedSupervisor}
          onSupervisorProjectSelect={handleSupervisorProjectSelect}
          onTaskDetailPanelOpen={handleTaskDetailPanelOpen}
        >
          {children}
        </MainContent>
      </div>

      {/* ReportViewer モーダル（サイドバーからタスクがクリックされた場合） */}
      {selectedTaskForReport && selectedProject && (
        <ReportViewer
          projectName={selectedProject.name}
          task={selectedTaskForReport}
          onClose={handleReportViewerClose}
        />
      )}

      {/* ORDER_128: タスクログモーダル（FloatingProgressPanelからタスククリック時） */}
      {taskLogViewState && (
        <TaskLogModal
          taskId={taskLogViewState.taskId}
          projectId={taskLogViewState.projectId}
          logFile={taskLogViewState.logFile}
          hasError={taskLogViewState.hasError}
          onClose={handleTaskLogClose}
        />
      )}

      {/* ORDER_135 TASK_1152: タスク詳細パネル（集約：1箇所のみでレンダリング） */}
      {selectedTaskDetailId && selectedProject && (
        <TaskDetailPanel
          projectId={selectedProject.name}
          taskId={selectedTaskDetailId}
          onClose={handleTaskDetailPanelClose}
          onTaskClick={handleTaskDetailPanelTaskClick}
          mode="modal"
        />
      )}

      {/* フローティング進捗パネル（ORDER_042追加） */}
      <FloatingProgressPanel />
    </div>
  );
};
