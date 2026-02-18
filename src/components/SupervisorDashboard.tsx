/**
 * SupervisorDashboard.tsx
 *
 * 統括ダッシュボード - Supervisor配下プロジェクトの進捗表示
 * ORDER_060 / TASK_650
 */

import React, { useState, useEffect } from 'react';
import type { Supervisor, SupervisorDetail, SupervisorProject, XBacklog } from '../preload';
import { XBacklogList } from './XBacklogList';
import { PortfolioView } from './PortfolioView';

interface SupervisorDashboardProps {
  supervisor: Supervisor;
  onProjectSelect?: (project: SupervisorProject) => void;
}

/** 統括アイコン */
const SupervisorIcon: React.FC = () => (
  <svg className="w-8 h-8 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
  </svg>
);

/** プロジェクトカード */
const ProjectCard: React.FC<{
  project: SupervisorProject;
  onClick?: () => void;
}> = ({ project, onClick }) => {
  const statusColors: Record<string, string> = {
    IN_PROGRESS: 'bg-blue-100 text-blue-800',
    COMPLETED: 'bg-green-100 text-green-800',
    PLANNING: 'bg-yellow-100 text-yellow-800',
    ON_HOLD: 'bg-gray-100 text-gray-800',
  };

  return (
    <div
      className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-medium text-gray-900">{project.name}</h3>
        <span className={`px-2 py-1 rounded text-xs font-medium ${statusColors[project.status] || 'bg-gray-100 text-gray-800'}`}>
          {project.status}
        </span>
      </div>
      <div className="text-sm text-gray-500">
        {project.currentOrderId ? (
          <span>アクティブ: {project.currentOrderId}</span>
        ) : (
          <span>アクティブORDERなし</span>
        )}
      </div>
    </div>
  );
};

export const SupervisorDashboard: React.FC<SupervisorDashboardProps> = ({
  supervisor,
  onProjectSelect,
}) => {
  const [detail, setDetail] = useState<SupervisorDetail | null>(null);
  const [projects, setProjects] = useState<SupervisorProject[]>([]);
  const [xbacklogs, setXBacklogs] = useState<XBacklog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'projects' | 'xbacklog' | 'portfolio'>('projects');

  const fetchData = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [detailData, projectsData, xbacklogsData] = await Promise.all([
        window.electronAPI.getSupervisorDetail(supervisor.id),
        window.electronAPI.getProjectsBySupervisor(supervisor.id),
        window.electronAPI.getXBacklogs(supervisor.id),
      ]);
      setDetail(detailData);
      setProjects(projectsData);
      setXBacklogs(xbacklogsData);
    } catch (err) {
      console.error('[SupervisorDashboard] Failed to fetch data:', err);
      setError('データの取得に失敗しました');
    } finally {
      setLoading(false);
    }
  }, [supervisor.id]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // DB変更イベントの購読（ORDER_004 / TASK_011）
  // スクリプト実行完了・タスクステータス変更時にSupervisorデータを自動更新
  useEffect(() => {
    const unsubscribe = window.electronAPI.onDbChanged((event) => {
      console.log('[SupervisorDashboard] db:changed event received:', event.source, event.projectId);
      // Supervisorダッシュボードは複数プロジェクトを管理するため、全イベントで更新
      // ローディング表示は抑制して静かに更新
      Promise.all([
        window.electronAPI.getSupervisorDetail(supervisor.id),
        window.electronAPI.getProjectsBySupervisor(supervisor.id),
        window.electronAPI.getXBacklogs(supervisor.id),
      ]).then(([detailData, projectsData, xbacklogsData]) => {
        setDetail(detailData);
        setProjects(projectsData);
        setXBacklogs(xbacklogsData);
      }).catch((err) => {
        console.error('[SupervisorDashboard] Failed to refresh via db:changed:', err);
      });
    });

    return () => {
      unsubscribe();
    };
  }, [supervisor.id]);

  const refreshXBacklogs = async () => {
    try {
      const data = await window.electronAPI.getXBacklogs(supervisor.id);
      setXBacklogs(data);
    } catch (err) {
      console.error('[SupervisorDashboard] Failed to refresh xbacklogs:', err);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-purple-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        {error}
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* ヘッダー */}
      <div className="flex items-center gap-4 mb-6">
        <SupervisorIcon />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">{supervisor.name}</h1>
          {supervisor.description && (
            <p className="text-gray-500">{supervisor.description}</p>
          )}
        </div>
      </div>

      {/* 統計サマリ */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-500">配下プロジェクト</div>
          <div className="text-2xl font-bold text-gray-900">{detail?.projectCount || 0}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-500">横断バックログ</div>
          <div className="text-2xl font-bold text-gray-900">{detail?.xbacklogCount || 0}</div>
        </div>
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-500">アクティブプロジェクト</div>
          <div className="text-2xl font-bold text-gray-900">
            {projects.filter(p => p.status === 'IN_PROGRESS').length}
          </div>
        </div>
      </div>

      {/* タブ */}
      <div className="border-b border-gray-200 mb-4">
        <nav className="-mb-px flex space-x-8">
          <button
            onClick={() => setActiveTab('projects')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'projects'
                ? 'border-purple-500 text-purple-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            プロジェクト一覧
          </button>
          <button
            onClick={() => setActiveTab('xbacklog')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'xbacklog'
                ? 'border-purple-500 text-purple-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            横断バックログ ({xbacklogs.length})
          </button>
          <button
            onClick={() => setActiveTab('portfolio')}
            className={`py-2 px-1 border-b-2 font-medium text-sm ${
              activeTab === 'portfolio'
                ? 'border-indigo-500 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            ポートフォリオ
          </button>
        </nav>
      </div>

      {/* コンテンツ */}
      {activeTab === 'projects' ? (
        <div className="grid grid-cols-2 gap-4">
          {projects.map(project => (
            <ProjectCard
              key={project.id}
              project={project}
              onClick={() => onProjectSelect?.(project)}
            />
          ))}
          {projects.length === 0 && (
            <div className="col-span-2 text-center text-gray-500 py-8">
              配下プロジェクトがありません
            </div>
          )}
        </div>
      ) : activeTab === 'xbacklog' ? (
        <XBacklogList
          supervisorId={supervisor.id}
          xbacklogs={xbacklogs}
          onRefresh={refreshXBacklogs}
        />
      ) : (
        <PortfolioView
          supervisorId={supervisor.id}
          projects={projects}
        />
      )}
    </div>
  );
};
