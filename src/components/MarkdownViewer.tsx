/**
 * MarkdownViewer.tsx - 汎用Markdownレンダリングコンポーネント
 *
 * react-markdown + remark-gfm を使用し、Markdownをリッチテキストとして表示する。
 * 見出し・リスト・コードブロック・テーブル・チェックボックス・引用・インライン要素に対応。
 *
 * TASK_1123: Markdownレンダリングコンポーネント準備
 */

import React from 'react';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

/**
 * MarkdownViewerProps
 */
export interface MarkdownViewerProps {
  /** 表示するMarkdownコンテンツ */
  content: string;
  /** 追加のCSSクラス名 */
  className?: string;
}

/**
 * react-markdown 用カスタムコンポーネント定義
 * 既存のTailwind CSSスタイルに合わせたレンダリング
 */
const markdownComponents: Components = {
  // 見出し
  h1: ({ children }) => (
    <h1 className="text-2xl font-bold text-gray-900 mt-6 mb-3 pb-2 border-b border-gray-200">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-xl font-bold text-gray-800 mt-5 mb-2 pb-1 border-b border-gray-100">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-lg font-semibold text-gray-800 mt-4 mb-2">
      {children}
    </h3>
  ),
  h4: ({ children }) => (
    <h4 className="text-base font-semibold text-gray-700 mt-3 mb-1">
      {children}
    </h4>
  ),
  h5: ({ children }) => (
    <h5 className="text-sm font-semibold text-gray-700 mt-2 mb-1">
      {children}
    </h5>
  ),
  h6: ({ children }) => (
    <h6 className="text-sm font-medium text-gray-600 mt-2 mb-1">
      {children}
    </h6>
  ),

  // 段落
  p: ({ children }) => (
    <p className="my-1 text-gray-700 leading-relaxed">{children}</p>
  ),

  // 箇条書きリスト
  ul: ({ children }) => (
    <ul className="list-disc list-inside my-2 space-y-1 text-gray-700">
      {children}
    </ul>
  ),

  // 番号付きリスト
  ol: ({ children }) => (
    <ol className="list-decimal list-inside my-2 space-y-1 text-gray-700">
      {children}
    </ol>
  ),

  // リストアイテム
  li: ({ children }) => (
    <li className="leading-relaxed">{children}</li>
  ),

  // コードブロック
  pre: ({ children }) => (
    <pre className="bg-gray-100 rounded p-3 overflow-x-auto my-2 text-sm font-mono">
      {children}
    </pre>
  ),

  // インラインコード & コードブロック内コード
  code: ({ children, className }) => {
    // className に "language-xxx" が含まれる場合はコードブロック内のcode要素
    const isBlock = className && className.startsWith('language-');
    if (isBlock) {
      return <code className={className}>{children}</code>;
    }
    // インラインコード
    return (
      <code className="bg-gray-100 px-1 rounded text-sm font-mono text-red-600">
        {children}
      </code>
    );
  },

  // 引用
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-gray-300 pl-4 py-1 my-2 text-gray-600 italic">
      {children}
    </blockquote>
  ),

  // テーブル
  table: ({ children }) => (
    <div className="overflow-x-auto my-4">
      <table className="min-w-full border-collapse border border-gray-300 text-sm">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-gray-100">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="border border-gray-300 px-3 py-2 text-left font-semibold text-gray-700">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="border border-gray-300 px-3 py-2 text-gray-700">
      {children}
    </td>
  ),
  tr: ({ children }) => (
    <tr className="even:bg-gray-50 odd:bg-white">{children}</tr>
  ),

  // 水平線
  hr: () => <hr className="my-4 border-gray-300" />,

  // リンク
  a: ({ href, children }) => (
    <a
      href={href}
      className="text-blue-600 hover:underline"
      target="_blank"
      rel="noopener noreferrer"
    >
      {children}
    </a>
  ),

  // 太字
  strong: ({ children }) => (
    <strong className="font-semibold">{children}</strong>
  ),

  // 斜体
  em: ({ children }) => (
    <em className="italic">{children}</em>
  ),

  // チェックボックス付きリスト用 input
  input: ({ checked, type, ...rest }) => {
    if (type === 'checkbox') {
      return (
        <input
          type="checkbox"
          checked={checked}
          readOnly
          className="w-4 h-4 mr-2 align-middle"
          {...rest}
        />
      );
    }
    return <input type={type} {...rest} />;
  },
};

/**
 * MarkdownViewerコンポーネント
 *
 * Markdownコンテンツを受け取り、react-markdown + remark-gfm でリッチテキストとしてレンダリングする。
 * - 見出し（H1-H6）
 * - リスト（箇条書き、番号付き、チェックリスト）
 * - コードブロック / インラインコード
 * - テーブル（GFM）
 * - 引用
 * - 水平線
 * - インライン要素（太字、斜体、リンク）
 */
export const MarkdownViewer: React.FC<MarkdownViewerProps> = ({ content, className = '' }) => {
  if (!content || content.trim() === '') {
    return (
      <div className={`text-center py-8 text-gray-400 ${className}`}>
        <p>表示するコンテンツがありません</p>
      </div>
    );
  }

  return (
    <div className={`prose prose-sm max-w-none ${className}`}>
      <Markdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {content}
      </Markdown>
    </div>
  );
};
