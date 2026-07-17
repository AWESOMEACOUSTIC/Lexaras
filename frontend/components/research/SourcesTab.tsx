"use client";

import React, { useState } from "react";
import { ResearchResult, PaperSummary, ExtractedContext } from "../../types/research";

interface SourcesTabProps {
  result: ResearchResult;
}

function ContextAccordionItem({ ctx, index }: { ctx: ExtractedContext; index: number }) {
  const [isOpen, setIsOpen] = useState(false);
  const url = ctx.url || "—";
  const displayUrl = url.length > 75 ? `${url.slice(0, 75)}…` : url;

  return (
    <div className="border border-border-default bg-bg-card/40 rounded-lg overflow-hidden transition-all duration-300">
      {/* Header Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-3 flex items-center justify-between gap-3 text-left hover:bg-bg-card transition-colors focus:outline-none"
      >
        <span className="text-xs font-semibold text-text-primary flex items-center gap-2 truncate">
          <span className="text-accent flex-shrink-0">📄</span>
          <span className="truncate">{displayUrl}</span>
        </span>
        <svg
          className={`w-3.5 h-3.5 text-text-secondary transition-transform duration-300 flex-shrink-0 ${
            isOpen ? "transform rotate-180 text-accent" : ""
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Body Content */}
      <div
        className={`transition-all duration-300 ease-in-out ${
          isOpen ? "max-h-[800px] border-t border-border-subtle" : "max-h-0 overflow-hidden"
        }`}
      >
        <div className="p-4 flex flex-col gap-3.5 text-xs text-text-secondary leading-relaxed bg-bg-deep/40">
          <div>
            <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider block mb-1">
              Source URL
            </span>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-accent hover:underline break-all"
            >
              {url}
            </a>
          </div>

          {ctx.content_summary && (
            <div>
              <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider block mb-1">
                Content Summary
              </span>
              <p className="p-3 bg-bg-deep border border-border-subtle rounded-md text-text-secondary">
                {ctx.content_summary}
              </p>
            </div>
          )}

          {ctx.key_points && ctx.key_points.length > 0 && (
            <div>
              <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider block mb-1">
                Key Extracted Points
              </span>
              <ul className="flex flex-col gap-2">
                {ctx.key_points.map((kp, idx) => (
                  <li key={idx} className="flex gap-2 items-start pl-1">
                    <span className="text-accent font-semibold flex-shrink-0">›</span>
                    <div>{kp}</div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {ctx.methodology && (
            <div className="p-3 bg-accent-dim/20 border border-accent/10 rounded-md">
              <span className="text-[10px] font-bold text-accent-light uppercase tracking-wider block mb-1">
                Methodology
              </span>
              <p className="text-text-primary">{ctx.methodology}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function SourcesTab({ result }: SourcesTabProps) {
  const papers = result.discovered_papers || [];
  const contexts = result.extracted_contexts || [];

  if (papers.length === 0) {
    return (
      <div className="p-4 border border-border-default bg-bg-card/20 rounded-lg text-xs text-text-secondary leading-relaxed">
        No papers were discovered.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 animate-fade-in-up max-h-[70vh] overflow-y-auto pr-1">
      {/* 1. Papers section */}
      <div>
        <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">
          {papers.length} Papers Discovered
        </h3>

        <div className="flex flex-col gap-3">
          {papers.map((p, idx) => {
            const isScholar = p.source === "scholar";
            return (
              <div
                key={idx}
                className="p-4 bg-bg-card border border-border-subtle hover:border-border-hover rounded-xl flex flex-col gap-2 transition-all duration-300"
              >
                <div className="flex justify-between items-start gap-3">
                  <h4 className="text-xs font-bold text-white leading-normal">
                    {p.title || "Untitled"}
                  </h4>
                  {/* Badges container */}
                  <div className="flex gap-1.5 flex-shrink-0">
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider ${
                        isScholar
                          ? "bg-accent-dim text-accent-light border border-accent/15"
                          : "bg-blue-900/30 text-blue-400 border border-blue-800/30"
                      }`}
                    >
                      {isScholar ? "Scholar" : "Web"}
                    </span>
                    {p.publication_year && (
                      <span className="text-[9px] px-1.5 py-0.5 rounded font-semibold bg-bg-elevated text-text-secondary border border-border-subtle">
                        {p.publication_year}
                      </span>
                    )}
                  </div>
                </div>

                {p.authors && (
                  <div className="text-[10px] text-text-secondary font-medium">
                    {p.authors}
                  </div>
                )}

                {p.url && (
                  <div className="text-[10px] truncate">
                    <a
                      href={p.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-text-tertiary hover:text-accent transition-colors underline break-all"
                    >
                      {p.url}
                    </a>
                  </div>
                )}

                {p.relevance_note && (
                  <div className="mt-1 text-[10px] text-text-muted italic border-l border-border-default pl-2">
                    {p.relevance_note}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Divider */}
      {contexts.length > 0 && <hr className="border-border-subtle" />}

      {/* 2. Contexts section */}
      {contexts.length > 0 && (
        <div>
          <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">
            {contexts.length} Papers Extracted
          </h3>

          <div className="flex flex-col gap-2">
            {contexts.map((ctx, idx) => (
              <ContextAccordionItem key={idx} ctx={ctx} index={idx} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
