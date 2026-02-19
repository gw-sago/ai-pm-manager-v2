import React, { useState } from 'react';

interface ManualModalProps {
  onClose: () => void;
}

interface Section {
  id: string;
  title: string;
  content: React.ReactNode;
}

const sections: Section[] = [
  {
    id: 'project-create',
    title: 'プロジェクト作成',
    content: (
      <div className="space-y-3 text-sm text-gray-300">
        <p>新しいプロジェクトを作成する手順です。</p>
        <ol className="list-decimal list-inside space-y-2">
          <li>左サイドバー上部の <strong className="text-white">「＋ 新規プロジェクト」</strong> ボタンをクリックします。</li>
          <li>プロジェクト名（英数字・アンダースコア）を入力します。</li>
          <li>説明（任意）を入力して <strong className="text-white">「作成」</strong> をクリックします。</li>
          <li>作成されたプロジェクトがサイドバーに表示されます。</li>
        </ol>
        <div className="bg-gray-700 rounded p-3 text-xs">
          <span className="text-yellow-400">ヒント:</span> プロジェクト名はシステム内部IDとして使用されます。作成後の変更はできません。
        </div>
      </div>
    ),
  },
  {
    id: 'backlog-add',
    title: 'バックログ追加',
    content: (
      <div className="space-y-3 text-sm text-gray-300">
        <p>プロジェクトにバックログ項目を追加する手順です。</p>
        <ol className="list-decimal list-inside space-y-2">
          <li>左サイドバーでプロジェクトを選択します。</li>
          <li><strong className="text-white">「バックログ」</strong> タブをクリックします。</li>
          <li><strong className="text-white">「＋ バックログ追加」</strong> ボタンをクリックします。</li>
          <li>タイトル、説明、優先度（P0〜P3）を入力します。</li>
          <li><strong className="text-white">「追加」</strong> をクリックして保存します。</li>
        </ol>
        <div className="bg-gray-700 rounded p-3 text-xs">
          <span className="text-blue-400">CLIコマンド:</span>
          <code className="block mt-1 text-green-400">/aipm-backlog-add</code>
        </div>
      </div>
    ),
  },
  {
    id: 'order-create',
    title: 'ORDER作成（PM実行）',
    content: (
      <div className="space-y-3 text-sm text-gray-300">
        <p>バックログからORDERを作成し、PM実行でタスクを自動分解します。</p>
        <ol className="list-decimal list-inside space-y-2">
          <li><strong className="text-white">「バックログ」</strong> タブでバックログ項目を選択します。</li>
          <li><strong className="text-white">「PM実行」</strong> をクリックすると、ORDER化とタスク自動分解が実行されます。</li>
        </ol>
        <div className="bg-gray-700 rounded p-3 text-xs">
          <span className="text-blue-400">CLIコマンド:</span>
          <code className="block mt-1 text-green-400">/aipm-backlog-to-order  # ORDER化</code>
          <code className="block text-green-400">/aipm-pm                # PM実行（タスク分解）</code>
        </div>
      </div>
    ),
  },
  {
    id: 'worker-exec',
    title: 'Worker実行',
    content: (
      <div className="space-y-3 text-sm text-gray-300">
        <p>PM実行で分解されたタスクをWorkerに実行させます。レビューも自動で行われます。</p>
        <ol className="list-decimal list-inside space-y-2">
          <li><strong className="text-white">「ORDER」</strong> タブでORDERを選択します。</li>
          <li>ステータスが <span className="text-yellow-400">QUEUED</span> のタスクを確認します。</li>
          <li>タスク詳細パネルの <strong className="text-white">「Worker実行」</strong> ボタンをクリックします。</li>
          <li>Workerが自動的にタスクを処理・レビューし、ステータスが <span className="text-green-400">COMPLETED</span> に変わります。</li>
        </ol>
        <div className="bg-gray-700 rounded p-3 text-xs">
          <span className="text-blue-400">CLIコマンド:</span>
          <code className="block mt-1 text-green-400">/aipm-worker            # 個別タスク実行</code>
          <code className="block text-green-400">/aipm-full-auto PROJECT BACKLOG_XXX  # 全自動（ORDER化→PM→Worker→レビュー）</code>
        </div>
        <div className="bg-gray-700 rounded p-3 text-xs mt-2">
          <span className="text-yellow-400">ヒント:</span> UI操作が途中で止まった場合は、ターミナルから <code className="text-green-400">/aipm-full-auto</code> を実行すると復旧できます。
        </div>
      </div>
    ),
  },
  {
    id: 'terminal',
    title: 'ターミナル操作',
    content: (
      <div className="space-y-3 text-sm text-gray-300">
        <p>Claude Code のターミナルからスラッシュコマンドで操作できます。UI操作が途中で止まった場合の復旧にも使えます。</p>

        <div className="bg-gray-700 rounded p-3 text-xs space-y-2">
          <p className="text-white font-medium mb-1">主要コマンド</p>
          <div className="space-y-1">
            <code className="block text-green-400">/aipm-full-auto PROJECT BACKLOG_XXX</code>
            <span className="text-gray-400 ml-4">ORDER化→PM→Worker→レビューを全自動実行</span>
          </div>
          <div className="space-y-1">
            <code className="block text-green-400">/aipm-backlog-to-order</code>
            <span className="text-gray-400 ml-4">バックログをORDERに昇格</span>
          </div>
          <div className="space-y-1">
            <code className="block text-green-400">/aipm-pm</code>
            <span className="text-gray-400 ml-4">PM実行（タスク自動分解）</span>
          </div>
          <div className="space-y-1">
            <code className="block text-green-400">/aipm-worker</code>
            <span className="text-gray-400 ml-4">Worker実行（タスク実装）</span>
          </div>
          <div className="space-y-1">
            <code className="block text-green-400">/aipm-status</code>
            <span className="text-gray-400 ml-4">プロジェクトの詳細状態確認</span>
          </div>
          <div className="space-y-1">
            <code className="block text-green-400">/aipm-recover</code>
            <span className="text-gray-400 ml-4">中断タスクのリカバリ</span>
          </div>
        </div>

        <div className="bg-gray-700 rounded p-3 text-xs">
          <span className="text-yellow-400">復旧ヒント:</span> UI操作（PM実行・Worker実行）が途中で止まった場合は、ターミナルから <code className="text-green-400">/aipm-full-auto PROJECT BACKLOG_XXX</code> を実行すると復旧できます。
        </div>

        <div className="bg-gray-700 rounded p-3 text-xs">
          <span className="text-blue-400">その他のコマンド:</span>
          <div className="mt-1 space-y-0.5">
            <code className="block text-green-400">/aipm-backlog-add</code>
            <code className="block text-green-400">/aipm-release</code>
            <code className="block text-green-400">/aipm-rollback</code>
            <code className="block text-green-400">/aipm-dashboard-update</code>
          </div>
        </div>
      </div>
    ),
  },
  {
    id: 'release',
    title: 'リリース',
    content: (
      <div className="space-y-3 text-sm text-gray-300">
        <p>ORDERのすべてのタスクが承認されたらリリースを実行します。</p>
        <ol className="list-decimal list-inside space-y-2">
          <li>全タスクのステータスが <span className="text-green-400">APPROVED</span> になったことを確認します。</li>
          <li>ORDERの詳細パネルで <strong className="text-white">「リリース」</strong> ボタンをクリックします。</li>
          <li>リリースノートを確認・編集します。</li>
          <li><strong className="text-white">「リリース実行」</strong> をクリックして完了します。</li>
          <li>ORDERのステータスが <span className="text-purple-400">RELEASED</span> に変わります。</li>
        </ol>
        <div className="bg-gray-700 rounded p-3 text-xs">
          <span className="text-blue-400">CLIコマンド:</span>
          <code className="block mt-1 text-green-400">/aipm-release         # リリース処理</code>
          <code className="block text-green-400">/aipm-release-review  # 承認フロー</code>
        </div>
      </div>
    ),
  },
];

export const ManualModal: React.FC<ManualModalProps> = ({ onClose }) => {
  const [activeSection, setActiveSection] = useState<string>(sections[0].id);

  const currentSection = sections.find(s => s.id === activeSection) ?? sections[0];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 rounded-xl shadow-2xl w-[800px] max-w-[95vw] h-[560px] max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-700 bg-gray-800 rounded-t-xl">
          <div className="flex items-center gap-2">
            <svg
              className="w-5 h-5 text-blue-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.746 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
              />
            </svg>
            <h2 className="text-base font-semibold text-white">使い方マニュアル</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
            title="閉じる"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* ボディ */}
        <div className="flex flex-1 overflow-hidden">
          {/* サイドナビ */}
          <nav className="w-48 flex-shrink-0 border-r border-gray-700 bg-gray-850 overflow-y-auto">
            <ul className="py-2">
              {sections.map((section) => (
                <li key={section.id}>
                  <button
                    onClick={() => setActiveSection(section.id)}
                    className={`w-full text-left px-4 py-2.5 text-sm transition-colors ${
                      activeSection === section.id
                        ? 'bg-blue-600 text-white font-medium'
                        : 'text-gray-400 hover:text-white hover:bg-gray-700'
                    }`}
                  >
                    {section.title}
                  </button>
                </li>
              ))}
            </ul>
          </nav>

          {/* コンテンツ */}
          <div className="flex-1 overflow-y-auto p-5">
            <h3 className="text-base font-semibold text-white mb-4 pb-2 border-b border-gray-700">
              {currentSection.title}
            </h3>
            {currentSection.content}
          </div>
        </div>

        {/* フッター */}
        <div className="px-5 py-2 border-t border-gray-700 bg-gray-800 rounded-b-xl">
          <p className="text-xs text-gray-500 text-center">
            AI PM Manager V2 — CLIコマンドは Claude Code のターミナルから実行できます
          </p>
        </div>
      </div>
    </div>
  );
};
