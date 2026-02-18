/**
 * ProjectInfo Component
 *
 * PROJECT_INFO.md の内容をMarkdown形式で表示するコンポーネント
 * ORDER_002 / BACKLOG_002
 */

import React, { useState, useEffect } from 'react';
import { MarkdownViewer } from './MarkdownViewer';

interface ProjectInfoProps {
  projectId: string;
}

/**
 * プロジェクト情報表示コンポーネント
 * PROJECT_INFO.md ファイルの内容をMarkdownViewerでレンダリングする
 */
export const ProjectInfo: React.FC<ProjectInfoProps> = ({ projectId }) => {
  const [content, setContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;

    const loadProjectInfo = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const mdContent = await window.electronAPI.getProjectInfoFile(projectId);
        if (mdContent) {
          setContent(mdContent);
        } else {
          setError('PROJECT_INFO.md が見つかりません');
        }
      } catch (err) {
        console.error('[ProjectInfo] Failed to load PROJECT_INFO.md:', err);
        setError('プロジェクト情報の読み込みに失敗しました');
      } finally {
        setIsLoading(false);
      }
    };

    loadProjectInfo();
  }, [projectId]);

  if (isLoading) {
    return (
      <div className="p-4">
        <div className="text-gray-500">読み込み中...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <div className="text-gray-500">{error}</div>
      </div>
    );
  }

  if (!content) {
    return null;
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <MarkdownViewer content={content} />
    </div>
  );
};
