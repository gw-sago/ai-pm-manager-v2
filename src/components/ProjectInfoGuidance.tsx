/**
 * ProjectInfoGuidance.tsx - 初回ガイダンスUIコンポーネント
 *
 * プロジェクト情報が未作成の場合に表示し、
 * プロジェクト関連情報の入力を促してバックログに登録する。
 */

import React, { useState } from 'react';

interface ProjectInfoGuidanceProps {
  projectId: string;
}

const TEMPLATE = `## プロジェクト基本情報
- リポジトリパス:
- 開発フォルダ:
- Gitリポジトリ URL:
- 仕様書・ドキュメント:

## 技術スタック
- 言語:
- フレームワーク:
- DB:
- その他ツール:

## プロジェクト概要
- 目的:
- 主な機能:
- 対象ユーザー:

## 開発環境
- OS:
- エディタ/IDE:
- ビルドコマンド:
- テストコマンド:

## 備考
`;

export const ProjectInfoGuidance: React.FC<ProjectInfoGuidanceProps> = ({ projectId }) => {
  const [title, setTitle] = useState('プロジェクト基本情報の整理');
  const [description, setDescription] = useState(TEMPLATE);
  const [priority, setPriority] = useState<'High' | 'Medium' | 'Low'>('High');
  const [category, setCategory] = useState('ドキュメント');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSkipped, setIsSkipped] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  const handleSubmit = async () => {
    if (!title.trim()) {
      setError('タイトルを入力してください');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const result = await window.electronAPI.addBacklog(
        projectId,
        title.trim(),
        description.trim() || null,
        priority,
        category.trim() || undefined
      );
      if (result && result.success) {
        setIsSubmitted(true);
      } else {
        setError(result?.error || 'バックログの追加に失敗しました');
      }
    } catch {
      setError('バックログの追加に失敗しました');
    } finally {
      setSubmitting(false);
    }
  };

  // スキップ状態
  if (isSkipped) {
    return (
      <div className="p-4">
        <div className="text-gray-500">プロジェクト情報が見つかりません</div>
        <button
          onClick={() => setIsSkipped(false)}
          className="text-sm text-blue-500 hover:text-blue-700 mt-2"
        >
          ガイダンスを表示
        </button>
      </div>
    );
  }

  // 登録完了状態
  if (isSubmitted) {
    return (
      <div className="p-4">
        <div className="bg-white rounded-lg shadow p-8 max-w-2xl mx-auto text-center">
          <div className="text-green-500 mb-4">
            <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">バックログに登録しました</h2>
          <p className="text-gray-600 text-sm leading-relaxed">
            バックログ一覧からORDER化してAIを実行すると、<br />
            プロジェクト情報ページが自動生成されます。
          </p>
          <div className="mt-6 bg-blue-50 rounded-lg p-4 text-left">
            <p className="text-sm font-medium text-blue-800 mb-2">次のステップ（UI操作）:</p>
            <ol className="text-sm text-blue-700 space-y-1 list-decimal list-inside">
              <li>「バックログ」タブを開く</li>
              <li>登録したバックログを選択し「ORDER化」する</li>
              <li>「PM実行」でタスクを自動分解</li>
              <li>「Worker実行」でAIがプロジェクト情報を生成</li>
            </ol>
          </div>
          <div className="mt-4 bg-gray-50 rounded-lg p-4 text-left border border-gray-200">
            <p className="text-sm font-medium text-gray-800 mb-2">ターミナルからの操作（Claude Code）:</p>
            <p className="text-xs text-gray-600 mb-2">
              スラッシュコマンドで同じ操作がターミナルから実行できます。<br />
              UI操作が途中で止まった場合の復旧にも使えます。
            </p>
            <div className="space-y-1.5 font-mono text-xs">
              <div className="flex items-start gap-2">
                <span className="text-gray-400 select-none shrink-0">$</span>
                <code className="text-gray-700">/aipm-backlog-to-order {projectId} BACKLOG_001</code>
                <span className="text-gray-400 ml-auto shrink-0">ORDER化</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-gray-400 select-none shrink-0">$</span>
                <code className="text-gray-700">/aipm-full-auto {projectId} BACKLOG_001</code>
                <span className="text-gray-400 ml-auto shrink-0">全自動実行</span>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              full-autoはORDER化からWorker実行まで一括で処理します。
            </p>
          </div>
        </div>
      </div>
    );
  }

  // ガイダンスフォーム
  return (
    <div className="p-4">
      <div className="bg-white rounded-lg shadow max-w-3xl mx-auto">
        {/* ヘッダー */}
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-start gap-3">
            <div className="text-blue-500 mt-0.5">
              <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-900">プロジェクト情報をまとめましょう</h2>
              <p className="text-sm text-gray-600 mt-1">
                プロジェクトの基本情報を入力してバックログに登録すると、AIが自動でプロジェクト情報ページを生成します。
              </p>
            </div>
          </div>
          {/* ステップ表示 */}
          <div className="flex items-center gap-2 mt-4 text-xs text-gray-500 flex-wrap">
            <span className="flex items-center gap-1 bg-blue-100 text-blue-700 px-2 py-1 rounded-full font-medium">
              1. 情報入力
            </span>
            <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="px-2 py-1">2. ORDER化</span>
            <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="px-2 py-1">3. PM実行</span>
            <svg className="w-3 h-3 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span className="px-2 py-1">4. Worker実行</span>
          </div>
        </div>

        {/* フォーム */}
        <div className="p-6 space-y-4">
          {/* タイトル */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">タイトル</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              maxLength={200}
            />
          </div>

          {/* 説明（テンプレート） */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              プロジェクト情報（わかる範囲で入力してください）
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={18}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
            />
            <p className="mt-1 text-xs text-gray-500">
              Markdown記法が使用できます。空欄の項目はそのままでも登録できます。
            </p>
          </div>

          {/* 優先度・カテゴリ */}
          <div className="flex gap-4">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">優先度</label>
              <select
                value={priority}
                onChange={(e) => setPriority(e.target.value as 'High' | 'Medium' | 'Low')}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
              >
                <option value="High">High - 優先度高</option>
                <option value="Medium">Medium - 通常</option>
                <option value="Low">Low - 優先度低</option>
              </select>
            </div>
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">カテゴリ</label>
              <input
                type="text"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm"
                maxLength={50}
              />
            </div>
          </div>

          {/* エラー表示 */}
          {error && (
            <div className="text-red-600 text-sm bg-red-50 rounded-lg p-3">{error}</div>
          )}
        </div>

        {/* フッター */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-lg">
          <button
            onClick={() => setIsSkipped(true)}
            className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            スキップ
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-5 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? '登録中...' : '登録する'}
          </button>
        </div>
      </div>
    </div>
  );
};
