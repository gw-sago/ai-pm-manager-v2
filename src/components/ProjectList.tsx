import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ProjectCard } from './ProjectCard';
import type { Project, ProjectListResult, ProjectStateChangedEvent, DataSource, Supervisor } from '../preload';

// ============================================================
// プロジェクト作成モーダル（ORDER_002 / BACKLOG_001）
// ============================================================
const CreateProjectModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  onCreated: () => void;
}> = ({ isOpen, onClose, onCreated }) => {
  const [projectId, setProjectId] = useState('');
  const [projectName, setProjectName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setProjectId('');
      setProjectName('');
      setError(null);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId.trim()) {
      setError('プロジェクトIDを入力してください');
      return;
    }
    if (!/^[A-Za-z][A-Za-z0-9_]*$/.test(projectId.trim())) {
      setError('IDは英字で始まり、英数字とアンダースコアのみ使用できます');
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      const result = await window.electronAPI.createProject(
        projectId.trim(),
        projectName.trim() || undefined,
      );
      if (result.success) {
        onCreated();
        onClose();
      } else {
        setError(result.error || '作成に失敗しました');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-lg shadow-xl w-96 p-5">
        <h3 className="text-base font-semibold text-gray-900 mb-4">
          プロジェクト作成
        </h3>
        <form onSubmit={handleSubmit}>
          <div className="mb-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              プロジェクトID <span className="text-red-500">*</span>
            </label>
            <input
              ref={inputRef}
              type="text"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              placeholder="My_Project"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
              disabled={isSubmitting}
            />
            <p className="mt-1 text-xs text-gray-500">
              英字で始まり、英数字とアンダースコアが使用可能
            </p>
          </div>
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              表示名
            </label>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="（省略時はIDと同じ）"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
              disabled={isSubmitting}
            />
          </div>
          {error && (
            <div className="mb-3 p-2 bg-red-50 text-red-700 text-xs rounded border border-red-200">
              {error}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 text-sm text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md"
              disabled={isSubmitting}
            >
              キャンセル
            </button>
            <button
              type="submit"
              className="px-3 py-1.5 text-sm text-white bg-blue-600 hover:bg-blue-700 rounded-md disabled:opacity-50"
              disabled={isSubmitting}
            >
              {isSubmitting ? '作成中...' : '作成'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// ============================================================
// プロジェクト削除確認ダイアログ（ORDER_002 / BACKLOG_001）
// ============================================================
const DeleteProjectDialog: React.FC<{
  projectId: string | null;
  onClose: () => void;
  onDeleted: () => void;
}> = ({ projectId, onClose, onDeleted }) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
  }, [projectId]);

  const handleDelete = async () => {
    if (!projectId) return;
    setIsDeleting(true);
    setError(null);
    try {
      const result = await window.electronAPI.deleteProject(projectId, true);
      if (result.success) {
        onDeleted();
        onClose();
      } else {
        setError(result.error || '削除に失敗しました');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsDeleting(false);
    }
  };

  if (!projectId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
      <div className="bg-white rounded-lg shadow-xl w-96 p-5">
        <h3 className="text-base font-semibold text-red-700 mb-3">
          プロジェクト削除
        </h3>
        <p className="text-sm text-gray-700 mb-2">
          プロジェクト <strong>{projectId}</strong> を削除しますか？
        </p>
        <p className="text-xs text-red-600 mb-4">
          関連するORDER、タスク、バックログも全て削除されます。この操作は取り消せません。
        </p>
        {error && (
          <div className="mb-3 p-2 bg-red-50 text-red-700 text-xs rounded border border-red-200">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 text-sm text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-md"
            disabled={isDeleting}
          >
            キャンセル
          </button>
          <button
            type="button"
            onClick={handleDelete}
            className="px-3 py-1.5 text-sm text-white bg-red-600 hover:bg-red-700 rounded-md disabled:opacity-50"
            disabled={isDeleting}
          >
            {isDeleting ? '削除中...' : '削除'}
          </button>
        </div>
      </div>
    </div>
  );
};

interface ProjectListProps {
  /**
   * プロジェクト選択時のコールバック
   */
  onProjectSelect?: (project: Project) => void;

  /**
   * 初期選択プロジェクト名
   */
  initialSelectedProject?: string;

  /**
   * コンパクト表示モード（サイドバー用）
   */
  compact?: boolean;

  /**
   * サイドバー折りたたみ状態
   */
  collapsed?: boolean;

  /**
   * Supervisor選択時のコールバック（ORDER_060追加）
   */
  onSupervisorSelect?: (supervisor: Supervisor) => void;

  /**
   * 現在選択中のSupervisor ID（ORDER_060追加）
   */
  selectedSupervisorId?: string;
}

/**
 * ローディング状態のスピナーUI（ORDER_051: 統一スタイル）
 *
 * スピナーアイコン + テキストで統一された表示
 */
const LoadingSpinner: React.FC<{ compact?: boolean; collapsed?: boolean }> = ({
  compact = false,
  collapsed = false,
}) => {
  // スピナーSVG
  const SpinnerIcon = ({ className = "w-5 h-5" }: { className?: string }) => (
    <svg
      className={`animate-spin text-blue-500 ${className}`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );

  if (collapsed) {
    return (
      <div className="flex flex-col items-center justify-center py-4">
        <SpinnerIcon className="w-6 h-6" />
      </div>
    );
  }

  if (compact) {
    return (
      <div className="flex items-center justify-center py-4 gap-2">
        <SpinnerIcon className="w-4 h-4" />
        <span className="text-xs text-gray-500">読み込み中...</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-8 gap-3">
      <SpinnerIcon className="w-6 h-6" />
      <span className="text-sm text-gray-500">読み込み中...</span>
    </div>
  );
};

/**
 * 後方互換性のためのエイリアス（既存コードで使用されている場合）
 */
const LoadingSkeleton = LoadingSpinner;

/**
 * エラー表示コンポーネント
 */
const ErrorDisplay: React.FC<{
  message: string;
  onRetry: () => void;
  compact?: boolean;
  collapsed?: boolean;
}> = ({ message, onRetry, compact = false, collapsed = false }) => {
  if (collapsed) {
    return (
      <button
        onClick={onRetry}
        className="w-10 h-10 flex items-center justify-center rounded-lg border border-red-200 bg-red-50 hover:bg-red-100"
        title={`エラー: ${message}`}
      >
        <svg className="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
        </svg>
      </button>
    );
  }

  if (compact) {
    return (
      <div className="text-center py-4 px-2">
        <button
          onClick={onRetry}
          className="text-xs text-red-600 hover:text-red-800 flex items-center justify-center w-full"
        >
          <svg className="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          再読込
        </button>
      </div>
    );
  }

  return (
    <div className="text-center py-8 px-4">
      <div className="inline-flex items-center justify-center w-12 h-12 bg-red-100 rounded-full mb-4">
        <svg
          className="w-6 h-6 text-red-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
          />
        </svg>
      </div>
      <h3 className="text-sm font-medium text-gray-900 mb-1">
        プロジェクト一覧の取得に失敗しました
      </h3>
      <p className="text-xs text-gray-500 mb-4">{message}</p>
      <button
        onClick={onRetry}
        className="inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
      >
        <svg
          className="w-3.5 h-3.5 mr-1.5"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        再読み込み
      </button>
    </div>
  );
};

/**
 * プロジェクトなし表示コンポーネント
 */
const EmptyState: React.FC<{ compact?: boolean; collapsed?: boolean }> = ({
  compact = false,
  collapsed = false,
}) => {
  if (collapsed) {
    return (
      <div
        className="w-10 h-10 flex items-center justify-center rounded-lg border border-gray-200 bg-gray-50"
        title="プロジェクトなし"
      >
        <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
        </svg>
      </div>
    );
  }

  if (compact) {
    return (
      <div className="text-center py-4 px-2">
        <p className="text-xs text-gray-400">プロジェクトなし</p>
      </div>
    );
  }

  return (
    <div className="text-center py-8 px-4">
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
            d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
          />
        </svg>
      </div>
      <h3 className="text-sm font-medium text-gray-900 mb-1">
        プロジェクトがありません
      </h3>
      <p className="text-xs text-gray-500">
        PROJECTS/ ディレクトリにプロジェクトを作成してください
      </p>
    </div>
  );
};

/**
 * プロジェクト一覧コンポーネント
 *
 * AI PM Frameworkからプロジェクト一覧を取得し、カード形式で表示します。
 * プロジェクト選択機能、リアルタイム更新、ローディング/エラー表示を提供します。
 */
export const ProjectList: React.FC<ProjectListProps> = ({
  onProjectSelect,
  initialSelectedProject,
  compact = false,
  collapsed = false,
  onSupervisorSelect,
  selectedSupervisorId,
}) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectName, setSelectedProjectName] = useState<string | null>(
    initialSelectedProject || null
  );
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [frameworkPath, setFrameworkPath] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<DataSource>('file');
  // ORDER_053: 初回ロード完了フラグ（チラつき防止用）
  const [isInitialLoadDone, setIsInitialLoadDone] = useState(false);
  // ORDER_060: Supervisor一覧
  const [supervisors, setSupervisors] = useState<Supervisor[]>([]);
  // ORDER_060: プロジェクトのSupervisor所属マップ
  const [projectSupervisorMap, setProjectSupervisorMap] = useState<Map<string, string>>(new Map());
  // ORDER_060: Supervisor展開状態
  const [expandedSupervisors, setExpandedSupervisors] = useState<Set<string>>(new Set());
  // ORDER_002: プロジェクト作成モーダル
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  // ORDER_002: プロジェクト削除ダイアログ
  const [deleteTargetProjectId, setDeleteTargetProjectId] = useState<string | null>(null);

  /**
   * プロジェクト一覧を取得
   *
   * ORDER_053: バックグラウンド更新対応
   * @param silent trueの場合、ローディング表示を抑制（定期リフレッシュ用）
   */
  const fetchProjects = useCallback(async (silent = false) => {
    try {
      // silentモード時、または初回ロード完了後はローディング表示をスキップ（チラつき防止）
      // ORDER_053: 初回ロード後はバックグラウンドで更新
      if (!silent && !isInitialLoadDone) {
        setIsLoading(true);
      }
      setError(null);

      // データソースを取得（ORDER_027: BACKLOG_069対応）
      try {
        const source = await window.electronAPI.getDataSource();
        setDataSource(source);
      } catch (e) {
        console.error('[ProjectList] Failed to get data source:', e);
      }

      const result: ProjectListResult = await window.electronAPI.getProjects();

      if (result.error) {
        setError(result.error);
        setProjects([]);
        setFrameworkPath(null);
      } else {
        setProjects(result.projects);
        setFrameworkPath(result.frameworkPath);

        // 初期選択がなく、プロジェクトが1つだけの場合は自動選択
        if (!selectedProjectName && result.projects.length === 1) {
          setSelectedProjectName(result.projects[0].name);
          onProjectSelect?.(result.projects[0]);
        }
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      setError(message);
      setProjects([]);
    } finally {
      setIsLoading(false);
      // ORDER_053: 初回ロード完了をマーク
      if (!isInitialLoadDone) {
        setIsInitialLoadDone(true);
      }
    }
  }, [selectedProjectName, onProjectSelect, isInitialLoadDone]);

  /**
   * プロジェクトSTATE変更イベントハンドラ
   */
  const handleStateChanged = useCallback(
    (event: ProjectStateChangedEvent) => {
      console.log('[ProjectList] State changed:', event);

      setProjects((prevProjects) => {
        return prevProjects.map((project) => {
          if (project.name === event.projectName) {
            return {
              ...project,
              state: event.state,
              lastUpdated: event.timestamp,
              hasStateFile: event.eventType !== 'unlink' && event.state !== null,
            };
          }
          return project;
        });
      });
    },
    []
  );

  /**
   * プロジェクト選択ハンドラ
   *
   * ORDER_016 FR-005: STATE.md不在時の動作対応
   * プロジェクト選択時に getProjectState() を呼び出し、
   * DB由来のstateデータを取得してからコールバックを呼ぶ。
   * これにより、STATE.mdが存在しなくてもDBからデータを取得できる。
   */
  const handleProjectClick = useCallback(
    async (project: Project) => {
      setSelectedProjectName(project.name);

      // stateがnullの場合、getProjectState()を呼び出してDBから取得
      if (!project.state) {
        try {
          const state = await window.electronAPI.getProjectState(project.name);
          if (state) {
            // stateが取得できた場合、projectsの状態を更新
            const updatedProject = { ...project, state };
            setProjects((prev) =>
              prev.map((p) => (p.name === project.name ? updatedProject : p))
            );
            onProjectSelect?.(updatedProject);
            return;
          }
        } catch (error) {
          console.error('[ProjectList] Failed to get project state:', error);
        }
      }

      // stateが既にある場合、または取得に失敗した場合はそのまま
      onProjectSelect?.(project);
    },
    [onProjectSelect]
  );

  /**
   * Supervisor一覧を取得（ORDER_060追加）
   */
  const fetchSupervisors = useCallback(async () => {
    try {
      const result = await window.electronAPI.getSupervisors();
      setSupervisors(result);

      // 各Supervisorのプロジェクトをマップにまとめる
      const newMap = new Map<string, string>();
      for (const sup of result) {
        try {
          const projects = await window.electronAPI.getProjectsBySupervisor(sup.id);
          for (const p of projects) {
            newMap.set(p.id, sup.id);
          }
        } catch (e) {
          console.error('[ProjectList] Failed to get projects for supervisor:', sup.id, e);
        }
      }
      setProjectSupervisorMap(newMap);

      // 全Supervisorを展開状態に
      setExpandedSupervisors(new Set(result.map(s => s.id)));
    } catch (error) {
      console.error('[ProjectList] Failed to fetch supervisors:', error);
    }
  }, []);

  /**
   * Supervisor展開/折りたたみ切り替え（ORDER_060追加）
   */
  const toggleSupervisor = useCallback((supervisorId: string) => {
    setExpandedSupervisors(prev => {
      const next = new Set(prev);
      if (next.has(supervisorId)) {
        next.delete(supervisorId);
      } else {
        next.add(supervisorId);
      }
      return next;
    });
  }, []);

  /**
   * Supervisorクリックハンドラ（ORDER_060追加）
   */
  const handleSupervisorClick = useCallback((supervisor: Supervisor) => {
    setSelectedProjectName(null); // プロジェクト選択をクリア
    onSupervisorSelect?.(supervisor);
  }, [onSupervisorSelect]);

  // 初回マウント時にプロジェクト一覧を取得
  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // 初回マウント時にSupervisor一覧も取得（ORDER_060追加）
  useEffect(() => {
    fetchSupervisors();
  }, [fetchSupervisors]);

  // STATE変更イベントの購読
  useEffect(() => {
    const unsubscribe = window.electronAPI.onProjectStateChanged(handleStateChanged);
    return () => {
      unsubscribe();
    };
  }, [handleStateChanged]);

  // メニュー更新イベントの購読（ORDER_063 / TASK_677）
  // ボタン操作・自動実行完了時にプロジェクト一覧を自動更新
  useEffect(() => {
    const unsubscribe = window.electronAPI.onMenuUpdate(() => {
      console.log('[ProjectList] menu:update event received, refreshing projects...');
      fetchProjects(true); // サイレントモードで更新（チラつき防止）
      fetchSupervisors(); // Supervisor一覧も更新
    });
    return () => {
      unsubscribe();
    };
  }, [fetchProjects, fetchSupervisors]);

  // DB変更イベントの購読（ORDER_004 / TASK_011）
  // スクリプト実行完了・タスクステータス変更・全タスク完了・タスククラッシュ時にプロジェクト一覧を自動更新
  useEffect(() => {
    const unsubscribe = window.electronAPI.onDbChanged((event) => {
      console.log('[ProjectList] db:changed event received:', event.source, event.projectId);
      fetchProjects(true); // サイレントモードで更新（チラつき防止）
      fetchSupervisors(); // Supervisor一覧も更新
    });
    return () => {
      unsubscribe();
    };
  }, [fetchProjects, fetchSupervisors]);

  // サイドバー折りたたみ時のレンダリング
  if (collapsed) {
    // ローディング中（初回ロードかつデータなしの場合のみスピナー表示）
    // ORDER_053: 既存データがある場合はチラつき防止のためスピナーを表示しない
    if (isLoading && projects.length === 0) {
      return <LoadingSkeleton collapsed />;
    }

    // エラー時
    if (error) {
      return <ErrorDisplay message={error} onRetry={() => fetchProjects(false)} collapsed />;
    }

    // プロジェクトなし
    if (projects.length === 0) {
      return <EmptyState collapsed />;
    }

    // プロジェクト一覧（折りたたみ時）
    return (
      <div className="flex flex-col items-center space-y-2">
        {projects.map((project) => (
          <ProjectCard
            key={project.name}
            project={project}
            isSelected={selectedProjectName === project.name}
            onClick={() => handleProjectClick(project)}
            collapsed
            dataSource={dataSource}
          />
        ))}
      </div>
    );
  }

  // コンパクト表示（サイドバー展開時）
  if (compact) {
    // ローディング中（初回ロードかつデータなしの場合のみスピナー表示）
    // ORDER_053: 既存データがある場合はチラつき防止のためスピナーを表示しない
    if (isLoading && projects.length === 0) {
      return (
        <div>
          <div className="flex items-center justify-between mb-2 px-1">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              プロジェクト
            </h3>
          </div>
          <LoadingSkeleton compact />
        </div>
      );
    }

    // エラー時
    if (error) {
      return (
        <div>
          <div className="flex items-center justify-between mb-2 px-1">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              プロジェクト
            </h3>
          </div>
          <ErrorDisplay message={error} onRetry={() => fetchProjects(false)} compact />
        </div>
      );
    }

    // プロジェクトなし
    if (projects.length === 0) {
      return (
        <div>
          <div className="flex items-center justify-between mb-2 px-1">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              プロジェクト
            </h3>
          </div>
          <EmptyState compact />
        </div>
      );
    }

    // プロジェクト一覧（コンパクト表示 - Supervisor階層対応 ORDER_060）
    // Supervisor所属プロジェクトと単独プロジェクトを分離
    const supervisorProjects = projects.filter(p => projectSupervisorMap.has(p.name));
    const standaloneProjects = projects.filter(p => !projectSupervisorMap.has(p.name));

    return (
      <div>
        {/* ヘッダー */}
        <div className="flex items-center justify-between mb-2 px-1">
          <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            プロジェクト
          </h3>
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => setIsCreateModalOpen(true)}
              className="p-1 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded transition-colors"
              title="プロジェクト作成"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
            <button
              onClick={() => fetchProjects(false)}
              className="p-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
              title="再読み込み"
            >
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
        </div>

        {/* Supervisor階層表示（ORDER_060追加） */}
        <div className="space-y-1">
          {supervisors.map((supervisor) => {
            const supProjects = supervisorProjects.filter(
              p => projectSupervisorMap.get(p.name) === supervisor.id
            );
            const isExpanded = expandedSupervisors.has(supervisor.id);
            const isSelected = selectedSupervisorId === supervisor.id;

            return (
              <div key={supervisor.id}>
                {/* Supervisorノード */}
                <div
                  className={`flex items-center px-2 py-1.5 rounded cursor-pointer text-sm ${
                    isSelected
                      ? 'bg-purple-100 text-purple-800'
                      : 'hover:bg-gray-100 text-gray-700'
                  }`}
                >
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleSupervisor(supervisor.id); }}
                    className="mr-1 p-0.5 hover:bg-gray-200 rounded"
                  >
                    <svg
                      className={`w-3 h-3 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                  <span
                    onClick={() => handleSupervisorClick(supervisor)}
                    className="flex-1 truncate font-medium"
                  >
                    {supervisor.name}
                  </span>
                  <span className="text-xs text-gray-400 ml-1">({supProjects.length})</span>
                </div>

                {/* 配下プロジェクト */}
                {isExpanded && (
                  <div className="ml-4 space-y-0.5">
                    {supProjects.map((project) => (
                      <div key={project.name} className="group relative">
                        <ProjectCard
                          project={project}
                          isSelected={selectedProjectName === project.name}
                          onClick={() => handleProjectClick(project)}
                          compact
                          dataSource={dataSource}
                        />
                        <button
                          onClick={(e) => { e.stopPropagation(); setDeleteTargetProjectId(project.name); }}
                          className="absolute right-1 top-1/2 -translate-y-1/2 p-0.5 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                          title={`${project.name} を削除`}
                        >
                          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          {/* 単独プロジェクト（Supervisor未所属） */}
          {standaloneProjects.length > 0 && (
            <div>
              {supervisors.length > 0 && (
                <div className="text-xs text-gray-400 uppercase px-2 py-1 mt-2">
                  単独プロジェクト
                </div>
              )}
              {standaloneProjects.map((project) => (
                <div key={project.name} className="group relative">
                  <ProjectCard
                    project={project}
                    isSelected={selectedProjectName === project.name}
                    onClick={() => handleProjectClick(project)}
                    compact
                    dataSource={dataSource}
                  />
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleteTargetProjectId(project.name); }}
                    className="absolute right-1 top-1/2 -translate-y-1/2 p-0.5 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                    title={`${project.name} を削除`}
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* フッター情報 */}
        <div className="mt-2 pt-2 border-t border-gray-200 text-xs text-gray-400 text-center">
          {projects.length} 件
        </div>

        {/* モーダル（ORDER_002 / BACKLOG_001） */}
        <CreateProjectModal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          onCreated={() => fetchProjects(false)}
        />
        <DeleteProjectDialog
          projectId={deleteTargetProjectId}
          onClose={() => setDeleteTargetProjectId(null)}
          onDeleted={() => {
            // 削除したプロジェクトが選択中だった場合、選択解除
            if (selectedProjectName === deleteTargetProjectId) {
              setSelectedProjectName(null);
            }
            fetchProjects(false);
          }}
        />
      </div>
    );
  }

  // 通常表示（メインエリア用）
  // ローディング中（初回ロードかつデータなしの場合のみスピナー表示）
  // ORDER_053: 既存データがある場合はチラつき防止のためスピナーを表示しない
  if (isLoading && projects.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">
            プロジェクト一覧
          </h2>
        </div>
        <LoadingSkeleton />
      </div>
    );
  }

  // エラー時
  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">
            プロジェクト一覧
          </h2>
        </div>
        <ErrorDisplay message={error} onRetry={() => fetchProjects(false)} />
      </div>
    );
  }

  // プロジェクトなし
  if (projects.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-800">
            プロジェクト一覧
          </h2>
        </div>
        <EmptyState />
      </div>
    );
  }

  // 正常表示
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
      {/* ヘッダー */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-800">
          プロジェクト一覧
        </h2>
        <button
          onClick={() => fetchProjects(false)}
          className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
          title="再読み込み"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      {/* フレームワークパス表示 */}
      {frameworkPath && (
        <div className="mb-4 p-2 bg-gray-50 rounded text-xs text-gray-500 truncate">
          <span className="font-medium">パス:</span> {frameworkPath}
        </div>
      )}

      {/* プロジェクトカード一覧 */}
      <div className="space-y-3">
        {projects.map((project) => (
          <ProjectCard
            key={project.name}
            project={project}
            isSelected={selectedProjectName === project.name}
            onClick={() => handleProjectClick(project)}
            dataSource={dataSource}
          />
        ))}
      </div>

      {/* フッター情報 */}
      <div className="mt-4 pt-3 border-t border-gray-200 text-xs text-gray-400 text-center">
        {projects.length} プロジェクト
      </div>
    </div>
  );
};
