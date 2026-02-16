/**
 * XBacklogDispatch.tsx
 *
 * 横断バックログ振り分けUI
 * ORDER_060 / TASK_653
 */

import React, { useState, useEffect } from 'react';
import type { XBacklog, XBacklogAnalysisResult, SupervisorProject } from '../preload';

interface XBacklogDispatchProps {
  xbacklog: XBacklog;
  onClose: () => void;
}

export const XBacklogDispatch: React.FC<XBacklogDispatchProps> = ({
  xbacklog,
  onClose,
}) => {
  const [analysis, setAnalysis] = useState<XBacklogAnalysisResult | null>(null);
  const [projects, setProjects] = useState<SupervisorProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>('');
  const [analyzing, setAnalyzing] = useState(false);
  const [dispatching, setDispatching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const data = await window.electronAPI.getProjectsBySupervisor(xbacklog.supervisorId);
        setProjects(data);
      } catch (err) {
        console.error('[XBacklogDispatch] Failed to fetch projects:', err);
      }
    };
    fetchProjects();
  }, [xbacklog.supervisorId]);

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError(null);
    try {
      const result = await window.electronAPI.analyzeXBacklog(xbacklog.id);
      setAnalysis(result);
      if (result?.suggestedProjectId) {
        setSelectedProjectId(result.suggestedProjectId);
      }
    } catch (err) {
      console.error('[XBacklogDispatch] Analysis failed:', err);
      setError('分析に失敗しました');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleDispatch = async () => {
    if (!selectedProjectId) {
      setError('振り分け先を選択してください');
      return;
    }

    setDispatching(true);
    setError(null);
    try {
      const result = await window.electronAPI.dispatchXBacklog(xbacklog.id, selectedProjectId);
      if (result.success) {
        onClose();
      } else {
        setError(result.error || '振り分けに失敗しました');
      }
    } catch (err) {
      console.error('[XBacklogDispatch] Dispatch failed:', err);
      setError('振り分けに失敗しました');
    } finally {
      setDispatching(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">横断バックログ振り分け</h2>
        </div>

        <div className="p-6">
          {/* バックログ情報 */}
          <div className="mb-4 bg-gray-50 rounded p-4">
            <div className="text-sm text-gray-500 mb-1">{xbacklog.id}</div>
            <div className="font-medium text-gray-900">{xbacklog.title}</div>
            {xbacklog.description && (
              <div className="text-sm text-gray-600 mt-2">{xbacklog.description}</div>
            )}
          </div>

          {error && (
            <div className="mb-4 bg-red-50 border border-red-200 rounded p-3 text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* 分析ボタン */}
          {!analysis && (
            <div className="mb-4">
              <button
                onClick={handleAnalyze}
                disabled={analyzing}
                className="w-full py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
              >
                {analyzing ? '分析中...' : '振り分け分析を実行'}
              </button>
            </div>
          )}

          {/* 分析結果 */}
          {analysis && (
            <div className="mb-4 bg-blue-50 border border-blue-200 rounded p-4">
              <div className="text-sm font-medium text-blue-800 mb-2">分析結果</div>
              <div className="text-sm text-blue-900">
                <div className="mb-1">
                  <span className="font-medium">推奨プロジェクト:</span>{' '}
                  {analysis.suggestedProjectName || '該当なし'}
                </div>
                <div className="mb-1">
                  <span className="font-medium">信頼度:</span>{' '}
                  {Math.round((analysis.confidence || 0) * 100)}%
                </div>
                <div>
                  <span className="font-medium">理由:</span>{' '}
                  {analysis.reason || '-'}
                </div>
              </div>
            </div>
          )}

          {/* プロジェクト選択 */}
          <div className="mb-6">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              振り分け先プロジェクト
            </label>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="w-full border border-gray-300 rounded px-3 py-2 focus:outline-none focus:ring-2 focus:ring-purple-500"
            >
              <option value="">選択してください</option>
              {projects.map(p => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.id})
                </option>
              ))}
            </select>
          </div>

          {/* ボタン */}
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded"
            >
              キャンセル
            </button>
            <button
              onClick={handleDispatch}
              disabled={dispatching || !selectedProjectId}
              className="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50"
            >
              {dispatching ? '振り分け中...' : '振り分け実行'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
