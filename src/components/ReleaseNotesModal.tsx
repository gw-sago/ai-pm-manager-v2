import React, { useState, useEffect } from 'react';

interface ReleaseEntry {
  version: string;
  date: string;
  sections: {
    type: string;
    items: string[];
  }[];
}

/**
 * CHANGELOG.md をパースしてバージョンエントリ一覧を返す
 */
function parseChangelog(content: string): ReleaseEntry[] {
  const entries: ReleaseEntry[] = [];
  const lines = content.split('\n');

  let currentEntry: ReleaseEntry | null = null;
  let currentSection: { type: string; items: string[] } | null = null;

  for (const line of lines) {
    // ## [x.y.z] - YYYY-MM-DD
    const versionMatch = line.match(/^##\s+\[([^\]]+)\]\s*-\s*(\S+)/);
    if (versionMatch) {
      if (currentSection && currentEntry) {
        currentEntry.sections.push(currentSection);
        currentSection = null;
      }
      if (currentEntry) {
        entries.push(currentEntry);
      }
      currentEntry = {
        version: versionMatch[1],
        date: versionMatch[2],
        sections: [],
      };
      continue;
    }

    if (!currentEntry) continue;

    // ### Added / Changed / Fixed / Removed
    const sectionMatch = line.match(/^###\s+(.+)/);
    if (sectionMatch) {
      if (currentSection) {
        currentEntry.sections.push(currentSection);
      }
      currentSection = { type: sectionMatch[1].trim(), items: [] };
      continue;
    }

    // - bullet items
    const bulletMatch = line.match(/^-\s+(.+)/);
    if (bulletMatch && currentSection) {
      currentSection.items.push(bulletMatch[1].trim());
      continue;
    }
  }

  // flush
  if (currentSection && currentEntry) {
    currentEntry.sections.push(currentSection);
  }
  if (currentEntry) {
    entries.push(currentEntry);
  }

  return entries;
}

function getSectionColor(type: string): string {
  switch (type.toLowerCase()) {
    case 'added':
      return 'text-green-400';
    case 'changed':
      return 'text-yellow-400';
    case 'fixed':
      return 'text-blue-400';
    case 'removed':
    case 'deprecated':
      return 'text-red-400';
    default:
      return 'text-gray-400';
  }
}

interface ReleaseEntryCardProps {
  entry: ReleaseEntry;
  defaultOpen: boolean;
}

const ReleaseEntryCard: React.FC<ReleaseEntryCardProps> = ({ entry, defaultOpen }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className="border border-gray-700 rounded-lg overflow-hidden">
      {/* バージョンヘッダー（クリックで折りたたみ） */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-800 hover:bg-gray-750 transition-colors text-left"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-expanded={isOpen}
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-bold text-white font-mono">v{entry.version}</span>
          <span className="text-xs text-gray-400">{entry.date}</span>
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* 変更内容（折りたたみ） */}
      {isOpen && (
        <div className="px-4 py-3 bg-gray-900 space-y-3">
          {entry.sections.map((section, i) => (
            <div key={i}>
              <div className={`text-xs font-semibold uppercase tracking-wide mb-1 ${getSectionColor(section.type)}`}>
                {section.type}
              </div>
              <ul className="space-y-1">
                {section.items.map((item, j) => (
                  <li key={j} className="flex items-start gap-2 text-sm text-gray-300">
                    <span className="text-gray-500 mt-0.5 flex-shrink-0">•</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {entry.sections.length === 0 && (
            <p className="text-sm text-gray-500">変更内容はありません。</p>
          )}
        </div>
      )}
    </div>
  );
};

interface ReleaseNotesModalProps {
  onClose: () => void;
}

export const ReleaseNotesModal: React.FC<ReleaseNotesModalProps> = ({ onClose }) => {
  const [entries, setEntries] = useState<ReleaseEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const result = await window.electronAPI?.getChangelog();
        if (!result) {
          setError('getChangelog APIが利用できません。');
          return;
        }
        if (!result.success || result.content == null) {
          setError(result.error ?? 'CHANGELOG.mdが見つかりません。');
          return;
        }
        setEntries(parseChangelog(result.content));
      } catch (err) {
        setError(String(err));
      } finally {
        setLoading(false);
      }
    };

    void load();
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-gray-900 rounded-xl shadow-2xl w-[640px] max-w-[95vw] h-[560px] max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-700 bg-gray-800 rounded-t-xl flex-shrink-0">
          <div className="flex items-center gap-2">
            <svg
              className="w-5 h-5 text-purple-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            <h2 className="text-base font-semibold text-white">リリースノート</h2>
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
        <div className="flex-1 overflow-y-auto p-5">
          {loading && (
            <div className="flex items-center justify-center h-full">
              <div className="text-gray-400 text-sm">読み込み中...</div>
            </div>
          )}

          {!loading && error && (
            <div className="flex items-center justify-center h-full">
              <div className="text-red-400 text-sm">{error}</div>
            </div>
          )}

          {!loading && !error && entries.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <div className="text-gray-400 text-sm">リリース情報がありません。</div>
            </div>
          )}

          {!loading && !error && entries.length > 0 && (
            <div className="space-y-3">
              {entries.map((entry, i) => (
                <ReleaseEntryCard key={entry.version} entry={entry} defaultOpen={i === 0} />
              ))}
            </div>
          )}
        </div>

        {/* フッター */}
        <div className="px-5 py-2 border-t border-gray-700 bg-gray-800 rounded-b-xl flex-shrink-0">
          <p className="text-xs text-gray-500 text-center">
            AI PM Manager V2 — 変更履歴
          </p>
        </div>
      </div>
    </div>
  );
};
