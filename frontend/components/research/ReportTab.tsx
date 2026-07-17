"use client";

import React from "react";
import { ResearchResult } from "../../types/research";

interface ReportTabProps {
  result: ResearchResult;
  topicLabel: string;
}

/**
 * A safe, lightweight Markdown-to-JSX parser that avoids dangerouslySetInnerHTML
 * and styles tags directly using Tailwind classes.
 */
function MarkdownRenderer({ content }: { content: string }) {
  if (!content) return null;

  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  
  let inList = false;
  let listItems: string[] = [];
  let inCodeBlock = false;
  let codeBlockContent: string[] = [];
  let codeBlockLang = "";

  const renderInlineText = (text: string): React.ReactNode[] => {
    // Basic regex parser for bold (**), inline code (`), and links ([text](url))
    const parts: React.ReactNode[] = [];
    let currentText = text;
    let keyIndex = 0;

    while (currentText.length > 0) {
      // Find matches for bold, code, link
      const boldMatch = currentText.match(/\*\*(.*?)\*\*/);
      const codeMatch = currentText.match(/`(.*?)`/);
      const linkMatch = currentText.match(/\[(.*?)\]\((.*?)\)/);

      // Identify which match comes first
      const indices = [
        boldMatch?.index !== undefined ? boldMatch.index : -1,
        codeMatch?.index !== undefined ? codeMatch.index : -1,
        linkMatch?.index !== undefined ? linkMatch.index : -1,
      ].filter(idx => idx >= 0);

      if (indices.length === 0) {
        // No inline formatting left
        parts.push(<span key={`text-${keyIndex++}`}>{currentText}</span>);
        break;
      }

      const firstIndex = Math.min(...indices);

      // Push text prior to the match
      if (firstIndex > 0) {
        parts.push(
          <span key={`text-${keyIndex++}`}>{currentText.slice(0, firstIndex)}</span>
        );
      }

      if (boldMatch && boldMatch.index === firstIndex) {
        parts.push(
          <strong key={`bold-${keyIndex++}`} className="font-semibold text-white">
            {boldMatch[1]}
          </strong>
        );
        currentText = currentText.slice(firstIndex + boldMatch[0].length);
      } else if (codeMatch && codeMatch.index === firstIndex) {
        parts.push(
          <code
            key={`code-${keyIndex++}`}
            className="font-mono text-xs text-accent bg-bg-deep px-1.5 py-0.5 rounded border border-border-subtle"
          >
            {codeMatch[1]}
          </code>
        );
        currentText = currentText.slice(firstIndex + codeMatch[0].length);
      } else if (linkMatch && linkMatch.index === firstIndex) {
        parts.push(
          <a
            key={`link-${keyIndex++}`}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent hover:underline break-all"
          >
            {linkMatch[1]}
          </a>
        );
        currentText = currentText.slice(firstIndex + linkMatch[0].length);
      }
    }

    return parts;
  };

  const flushList = (key: string) => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={key} className="list-disc pl-5 mb-4 text-xs text-text-secondary flex flex-col gap-1.5">
          {listItems.map((item, idx) => (
            <li key={`li-${idx}`} className="leading-relaxed">
              {renderInlineText(item)}
            </li>
          ))}
        </ul>
      );
      listItems = [];
      inList = false;
    }
  };

  const flushCodeBlock = (key: string) => {
    if (codeBlockContent.length > 0) {
      elements.push(
        <pre key={key} className="p-4 bg-bg-deep border border-border-default rounded-lg font-mono text-xs text-text-primary overflow-x-auto mb-4 leading-relaxed">
          {codeBlockLang && (
            <div className="text-[10px] text-text-muted mb-2 uppercase select-none border-b border-border-subtle pb-1">
              {codeBlockLang}
            </div>
          )}
          <code>{codeBlockContent.join("\n")}</code>
        </pre>
      );
      codeBlockContent = [];
      codeBlockLang = "";
      inCodeBlock = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const key = `block-${i}`;

    // Handle Code Block boundary
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        flushCodeBlock(key);
      } else {
        flushList(key);
        inCodeBlock = true;
        codeBlockLang = line.trim().slice(3) || "code";
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockContent.push(line);
      continue;
    }

    // Handle List Items
    const listMatch = line.match(/^(\s*)[-*+]\s+(.*)/);
    if (listMatch) {
      inList = true;
      listItems.push(listMatch[2]);
      continue;
    } else if (inList && line.trim() !== "") {
      // Continuation of list or end of list
      if (line.match(/^\s{2,}/)) {
        // Indented continuation - just append to last item
        listItems[listItems.length - 1] += "\n" + line.trim();
        continue;
      } else {
        flushList(key);
      }
    }

    // Standard headers
    if (line.startsWith("# ")) {
      flushList(key);
      elements.push(
        <h1 key={key} className="text-xl font-bold tracking-tight text-white mt-6 mb-3 border-b border-border-default pb-2">
          {renderInlineText(line.slice(2))}
        </h1>
      );
    } else if (line.startsWith("## ")) {
      flushList(key);
      elements.push(
        <h2 key={key} className="text-base font-semibold text-white mt-5 mb-2.5">
          {renderInlineText(line.slice(3))}
        </h2>
      );
    } else if (line.startsWith("### ")) {
      flushList(key);
      elements.push(
        <h3 key={key} className="text-sm font-semibold text-white mt-4 mb-2">
          {renderInlineText(line.slice(4))}
        </h3>
      );
    } else if (line.startsWith("> ")) {
      flushList(key);
      elements.push(
        <blockquote key={key} className="border-l-2 border-accent bg-bg-card/30 pl-4 py-2 pr-2 rounded-r-md text-xs italic text-accent-light mb-4 my-2 leading-relaxed">
          {renderInlineText(line.slice(2))}
        </blockquote>
      );
    } else if (line.trim() === "") {
      // Empty line closes active lists
      flushList(key);
    } else {
      // Normal paragraph
      elements.push(
        <p key={key} className="text-xs leading-relaxed text-text-secondary mb-4">
          {renderInlineText(line)}
        </p>
      );
    }
  }

  // Flush remaining buffers
  flushList(`final-list`);
  flushCodeBlock(`final-code`);

  return <div className="prose max-w-none">{elements}</div>;
}

export function ReportTab({ result, topicLabel }: ReportTabProps) {
  const draft = result.draft_report || "";

  const handleDownload = () => {
    if (!draft) return;
    const blob = new Blob([draft], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const safeTopic = topicLabel
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .slice(0, 40);
    a.href = url;
    a.download = `lexaras_${safeTopic || "report"}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (!draft || draft.startsWith("[WRITER_ERROR]")) {
    return (
      <div className="p-4 border border-red-custom/20 bg-red-dim rounded-lg text-xs text-red-light leading-relaxed">
        <strong>Writer Agent Error</strong>
        <p className="mt-1">
          The writer agent was unable to synthesize the final report. Please check the Debug tab for detailed process exceptions.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 animate-fade-in-up">
      {/* Report body frame */}
      <div className="p-6 bg-bg-card border border-border-subtle rounded-xl max-h-[70vh] overflow-y-auto shadow-sm">
        <MarkdownRenderer content={draft} />
      </div>

      {/* Download Action */}
      <div className="flex justify-end">
        <button
          onClick={handleDownload}
          className="h-10 px-4 text-xs font-semibold bg-bg-elevated border border-border-default text-white hover:text-accent hover:border-accent rounded-md flex items-center gap-2 transition-colors select-none"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
          </svg>
          Download as Markdown
        </button>
      </div>
    </div>
  );
}
