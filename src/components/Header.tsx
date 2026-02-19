import React, { useState } from 'react';
import { ManualModal } from './ManualModal';

interface HeaderProps {}

export const Header: React.FC<HeaderProps> = () => {
  const [isManualOpen, setIsManualOpen] = useState(false);

  return (
    <>
      <header className="h-12 bg-white border-b border-gray-200 flex items-center justify-between px-4 shadow-sm">
        <h1 className="text-lg font-semibold text-gray-800">AI PM Manager</h1>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setIsManualOpen(true)}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md transition-colors"
            aria-label="Open Manual"
            title="使い方マニュアル"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.746 0 3.332.477 4.5 1.253v13C19.832 18.477 18.246 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
              />
            </svg>
          </button>
          <button
            onClick={() => window.electronAPI?.openTerminal()}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md transition-colors"
            aria-label="Open Terminal"
            title="ターミナルを開く"
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              xmlns="http://www.w3.org/2000/svg"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
              />
            </svg>
          </button>
        </div>
      </header>
      {isManualOpen && <ManualModal onClose={() => setIsManualOpen(false)} />}
    </>
  );
};
