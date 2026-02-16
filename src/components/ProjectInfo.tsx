/**
 * ProjectInfo Component
 *
 * プロジェクト情報の表示・編集を行うコンポーネント
 * ORDER_156 / TASK_1233
 */

import React, { useState, useEffect } from 'react';

interface ProjectInfoData {
  id: number;
  name: string;
  path: string;
  description: string | null;
  purpose: string | null;
  tech_stack: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

interface ProjectInfoProps {
  projectId: string;
}

/**
 * プロジェクト情報表示・編集コンポーネント
 */
export const ProjectInfo: React.FC<ProjectInfoProps> = ({ projectId }) => {
  const [projectInfo, setProjectInfo] = useState<ProjectInfoData | null>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 編集フォームの状態
  const [editForm, setEditForm] = useState({
    description: '',
    purpose: '',
    tech_stack: '',
  });

  // プロジェクト情報を読み込み
  const loadProjectInfo = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const info = await window.electronAPI.getProjectInfo(projectId);
      if (info) {
        setProjectInfo(info);
        setEditForm({
          description: info.description || '',
          purpose: info.purpose || '',
          tech_stack: info.tech_stack || '',
        });
      } else {
        setError('プロジェクト情報が見つかりません');
      }
    } catch (err) {
      console.error('Failed to load project info:', err);
      setError('プロジェクト情報の読み込みに失敗しました');
    } finally {
      setIsLoading(false);
    }
  };

  // マウント時にデータを読み込む
  useEffect(() => {
    if (projectId) {
      loadProjectInfo();
    }
  }, [projectId]);

  // 編集開始
  const handleEdit = () => {
    setIsEditing(true);
  };

  // 編集キャンセル
  const handleCancel = () => {
    if (projectInfo) {
      setEditForm({
        description: projectInfo.description || '',
        purpose: projectInfo.purpose || '',
        tech_stack: projectInfo.tech_stack || '',
      });
    }
    setIsEditing(false);
  };

  // 保存処理
  const handleSave = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await window.electronAPI.updateProjectInfo(projectId, {
        description: editForm.description || undefined,
        purpose: editForm.purpose || undefined,
        tech_stack: editForm.tech_stack || undefined,
      });

      if (result.success) {
        // 成功したら再読み込み
        await loadProjectInfo();
        setIsEditing(false);
      } else {
        setError(result.error || '保存に失敗しました');
      }
    } catch (err) {
      console.error('Failed to save project info:', err);
      setError('保存に失敗しました');
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading && !projectInfo) {
    return (
      <div className="p-4">
        <div className="text-gray-500">読み込み中...</div>
      </div>
    );
  }

  if (error && !projectInfo) {
    return (
      <div className="p-4">
        <div className="text-red-600">{error}</div>
      </div>
    );
  }

  if (!projectInfo) {
    return null;
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-bold text-gray-900">プロジェクト情報</h2>
        {!isEditing && (
          <button
            onClick={handleEdit}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
            disabled={isLoading}
          >
            編集
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-100 text-red-700 rounded">
          {error}
        </div>
      )}

      <div className="space-y-4">
        {/* プロジェクト名（読み取り専用） */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            プロジェクト名
          </label>
          <div className="text-gray-900">{projectInfo.name}</div>
        </div>

        {/* パス（読み取り専用） */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            パス
          </label>
          <div className="text-gray-600 text-sm">{projectInfo.path}</div>
        </div>

        {/* ステータス（読み取り専用） */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            ステータス
          </label>
          <div className="text-gray-900">{projectInfo.status}</div>
        </div>

        {/* 概要 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            概要
          </label>
          {isEditing ? (
            <textarea
              value={editForm.description}
              onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={3}
              placeholder="プロジェクトの概要を入力してください"
            />
          ) : (
            <div className="text-gray-900 whitespace-pre-wrap">
              {projectInfo.description || '（未設定）'}
            </div>
          )}
        </div>

        {/* 目的 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            目的
          </label>
          {isEditing ? (
            <textarea
              value={editForm.purpose}
              onChange={(e) => setEditForm({ ...editForm, purpose: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={3}
              placeholder="プロジェクトの目的を入力してください"
            />
          ) : (
            <div className="text-gray-900 whitespace-pre-wrap">
              {projectInfo.purpose || '（未設定）'}
            </div>
          )}
        </div>

        {/* 技術スタック */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            技術スタック
          </label>
          {isEditing ? (
            <textarea
              value={editForm.tech_stack}
              onChange={(e) => setEditForm({ ...editForm, tech_stack: e.target.value })}
              className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              rows={3}
              placeholder="使用技術を入力してください"
            />
          ) : (
            <div className="text-gray-900 whitespace-pre-wrap">
              {projectInfo.tech_stack || '（未設定）'}
            </div>
          )}
        </div>

        {/* 編集モードの場合はボタン表示 */}
        {isEditing && (
          <div className="flex gap-2 pt-4">
            <button
              onClick={handleSave}
              disabled={isLoading}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors disabled:bg-gray-400"
            >
              {isLoading ? '保存中...' : '保存'}
            </button>
            <button
              onClick={handleCancel}
              disabled={isLoading}
              className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition-colors disabled:bg-gray-100"
            >
              キャンセル
            </button>
          </div>
        )}

        {/* 更新日時（読み取り専用） */}
        <div className="pt-4 border-t border-gray-200">
          <div className="text-sm text-gray-500">
            最終更新: {new Date(projectInfo.updated_at).toLocaleString('ja-JP')}
          </div>
        </div>
      </div>
    </div>
  );
};
