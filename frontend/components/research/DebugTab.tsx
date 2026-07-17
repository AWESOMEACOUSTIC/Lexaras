"use client";

import React, { useState } from "react";
import { ResearchResult } from "../../types/research";

interface DebugTabProps {
  result: ResearchResult;
}

export function DebugTab({ result }: DebugTabProps) {
  const [showRawDiscovery, setShowRawDiscovery] = useState(false);
  const queries = result.search_queries || [];
  const retryCount = result.retry_count || 0;
  const extractionErrors = result.extraction_errors || [];
  const errorLog = result.error_log || [];
  const discoveryRaw = result.discovery_raw || "—";

  return (
    <div className="flex flex-col gap-5 animate-fade-in-up max-h-[70vh] overflow-y-auto pr-1">
      {/* Search Queries Generated */}
      <div>
        <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">
          Search Queries Generated
        </h3>
        {queries.length > 0 ? (
          <div className="flex flex-col gap-2">
            {queries.map((q, idx) => (
              <div
                key={idx}
                className="flex items-center gap-3 p-3 bg-bg-card border border-border-subtle rounded-lg text-xs"
              >
                <div className="h-5 px-1.5 bg-bg-elevated border border-border-default rounded flex items-center justify-center font-mono font-semibold text-text-tertiary select-none">
                  Q{idx + 1}
                </div>
                <div className="font-mono text-text-primary truncate">{q}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-text-muted italic">None recorded.</div>
        )}
      </div>

      {/* Retry Warnings */}
      {retryCount > 0 && (
        <div className="p-3 border border-amber-custom/25 bg-amber-custom/10 text-amber-light rounded-lg text-xs flex items-center gap-2">
          <span>↻</span>
          <span>Discovery retried {retryCount} time(s) due to search restrictions or rate limits.</span>
        </div>
      )}

      {/* Errors & Pipeline warnings */}
      {(extractionErrors.length > 0 || errorLog.length > 0) && (
        <div>
          <h3 className="text-xs font-bold text-text-muted uppercase tracking-wider mb-3">
            Errors & Warnings
          </h3>
          <div className="flex flex-col gap-2">
            {extractionErrors.map((err, idx) => (
              <div
                key={`extract-${idx}`}
                className="p-3 border border-red-custom/15 bg-red-custom/5 text-red-light rounded-lg text-xs leading-normal"
              >
                <strong>Extraction error:</strong> {err}
              </div>
            ))}
            {errorLog.map((err, idx) => (
              <div
                key={`pipeline-${idx}`}
                className="p-3 border border-red-custom/15 bg-red-custom/5 text-red-light rounded-lg text-xs leading-normal"
              >
                <strong>Pipeline event warning:</strong> {err}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Raw Discovery log details */}
      <hr className="border-border-subtle" />
      <div>
        <button
          onClick={() => setShowRawDiscovery(!showRawDiscovery)}
          className="w-full px-4 py-3 bg-bg-card border border-border-subtle hover:border-border-hover rounded-xl flex items-center justify-between text-xs font-semibold text-text-secondary focus:outline-none transition-all duration-300"
        >
          <span>Raw Discovery Log Output</span>
          <svg
            className={`w-3.5 h-3.5 text-text-secondary transition-transform duration-300 ${
              showRawDiscovery ? "transform rotate-180 text-accent" : ""
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
          </svg>
        </button>

        {showRawDiscovery && (
          <div className="mt-3 p-4 bg-bg-deep border border-border-default rounded-xl font-mono text-[10px] text-text-tertiary leading-relaxed overflow-x-auto whitespace-pre max-h-64 shadow-inner">
            {discoveryRaw}
          </div>
        )}
      </div>
    </div>
  );
}
