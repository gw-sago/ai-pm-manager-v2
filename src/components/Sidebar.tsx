import React from 'react';
import type { Project, OrderInfo, Supervisor } from '../preload';
import { ProjectList } from './ProjectList';
import { OrderTree } from './OrderTree';

interface SidebarProps {
  collapsed?: boolean;
  onToggle?: () => void;
  /** 現在選択中のプロジェクト（Layout.tsxから渡される） */
  selectedProject?: Project | null;
  /** プロジェクト選択時のコールバック（Layout.tsxに通知） */
  onProjectSelect?: (project: Project) => void;
  /** 現在選択中のORDER ID（Layout.tsxから渡される） */
  selectedOrderId?: string | null;
  /** ORDER選択時のコールバック（Layout.tsxに通知） */
  onOrderSelect?: (order: OrderInfo) => void;
  /** 設定ボタンクリック時のコールバック（ORDER_152: 削除により未使用） */
  onSettingsClick?: () => void;
  /** 設定画面が表示中かどうか（ORDER_152: 削除により未使用） */
  isSettingsOpen?: boolean;
  /** 現在選択中のSupervisor（ORDER_060追加） */
  selectedSupervisor?: Supervisor | null;
  /** Supervisor選択時のコールバック（ORDER_060追加） */
  onSupervisorSelect?: (supervisor: Supervisor) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  collapsed = false,
  onToggle,
  selectedProject,
  onProjectSelect,
  selectedOrderId,
  onOrderSelect,
  // onSettingsClick, // ORDER_152: 削除により未使用
  // isSettingsOpen = false, // ORDER_152: 削除により未使用
  selectedSupervisor,
  onSupervisorSelect,
}) => {
  return (
    <aside
      className={`bg-white border-r border-gray-200 transition-all duration-300 ${
        collapsed ? 'w-16' : 'w-60'
      } flex flex-col`}
    >
      {/* Toggle button */}
      <div className="flex justify-end p-2">
        <button
          onClick={onToggle}
          className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          <svg
            className={`w-5 h-5 transform transition-transform ${collapsed ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
          </svg>
        </button>
      </div>

      {/* プロジェクト一覧（Supervisor階層対応） */}
      <div className={`${collapsed ? 'px-2' : 'px-3'} py-2`}>
        <ProjectList
          onProjectSelect={onProjectSelect}
          initialSelectedProject={selectedProject?.name}
          compact={true}
          collapsed={collapsed}
          onSupervisorSelect={onSupervisorSelect}
          selectedSupervisorId={selectedSupervisor?.id}
        />
      </div>

      {/* ORDER一覧（プロジェクト選択時のみ表示） */}
      {selectedProject && (
        <div className={`flex-1 overflow-auto ${collapsed ? 'px-2' : 'px-3'} py-2 border-t border-gray-200`}>
          <OrderTree
            project={selectedProject}
            selectedOrderId={selectedOrderId}
            onOrderSelect={onOrderSelect}
            compact={true}
            collapsed={collapsed}
          />
        </div>
      )}
    </aside>
  );
};
