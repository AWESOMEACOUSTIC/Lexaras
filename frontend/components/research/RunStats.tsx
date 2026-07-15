"use client";

import React from "react";
import { ResearchResult } from "../../types/research";

interface RunStatsProps {
  result: ResearchResult | null;
  papersDiscovered: number;
  elapsedSeconds: number;
}

export function RunStats({ result, papersDiscovered, elapsedSeconds }: RunStatsProps) {
  const papers = result ? result.discovered_papers?.length || 0 : papersDiscovered;
  
  // Calculate scholar vs web counts
  let numScholar = 0;
  let numWeb = 0;
  if (result) {
    numScholar = result.scholar_papers?.length ?? result.discovered_papers?.filter(p => p.source === "scholar").length ?? 0;
    numWeb = result.web_papers?.length ?? result.discovered_papers?.filter(p => p.source === "web").length ?? 0;
  }

  const extracted = result ? result.extracted_contexts?.length : null;
  const words = result ? result.draft_report?.split(/\s+/).filter(Boolean).length : null;
  const score = result?.evaluation?.overall_score;

  // Percentage split
  const totalSplit = numScholar + numWeb;
  const scholarPct = totalSplit > 0 ? (numScholar / totalSplit) * 100 : 0;
  const webPct = totalSplit > 0 ? (numWeb / totalSplit) * 100 : 0;

  // Dynamic color for score text
  const getScoreColorClass = (val: number) => {
    if (val >= 8.5) return "text-green-light";
    if (val >= 7.0) return "text-green-custom";
    if (val >= 5.0) return "text-amber-light";
    return "text-red-light";
  };

  return (
    <div className="flex flex-col gap-4 select-none animate-fade-in-up">
      <label className="block text-[0.65rem] font-bold uppercase tracking-wider text-text-muted">
        Run Stats
      </label>

      {/* 2x2 Metric Grid */}
      <div className="grid grid-cols-2 gap-2">
        <div className="p-3 bg-bg-card border border-border-subtle rounded-lg flex flex-col justify-between">
          <span className="text-[10px] font-semibold text-text-muted">Papers found</span>
          <span className="text-lg font-bold text-accent mt-1">{papers}</span>
          {result && totalSplit > 0 && (
            <span className="text-[9px] text-text-tertiary mt-0.5">
              {numScholar} scholar · {numWeb} web
            </span>
          )}
        </div>

        <div className="p-3 bg-bg-card border border-border-subtle rounded-lg flex flex-col justify-between">
          <span className="text-[10px] font-semibold text-text-muted">Extracted</span>
          <span className="text-lg font-bold text-text-primary mt-1">
            {extracted !== null ? extracted : "—"}
          </span>
          <span className="text-[9px] text-text-tertiary mt-0.5">key findings</span>
        </div>

        <div className="p-3 bg-bg-card border border-border-subtle rounded-lg flex flex-col justify-between">
          <span className="text-[10px] font-semibold text-text-muted">Report words</span>
          <span className="text-lg font-bold text-text-primary mt-1">
            {words !== null ? words.toLocaleString() : "—"}
          </span>
          <span className="text-[9px] text-text-tertiary mt-0.5">generated</span>
        </div>

        <div className="p-3 bg-bg-card border border-border-subtle rounded-lg flex flex-col justify-between">
          <span className="text-[10px] font-semibold text-text-muted">Overall score</span>
          <span className={`text-lg font-bold mt-1 ${score ? getScoreColorClass(score) : "text-text-muted"}`}>
            {score ? score.toFixed(1) : "—"}
          </span>
          <span className="text-[9px] text-text-tertiary mt-0.5">out of 10.0</span>
        </div>
      </div>

      {/* Source Split inline bar */}
      {result && totalSplit > 0 && (
        <div className="flex flex-col gap-1.5 mt-1">
          <div className="flex items-center justify-between text-[9px] text-text-tertiary font-medium">
            <span>Scholar {numScholar}</span>
            <span>Web {numWeb}</span>
          </div>
          <div className="h-1 w-full bg-border-subtle rounded-full overflow-hidden flex">
            <div
              style={{ width: `${scholarPct}%` }}
              className="h-full bg-accent transition-all duration-500"
            />
            <div
              style={{ width: `${webPct}%` }}
              className="h-full bg-[#3b82f6] transition-all duration-500"
            />
          </div>
        </div>
      )}

      {/* Elapsed row */}
      <div className="flex items-center justify-between border-t border-border-subtle pt-3 text-[10px] text-text-secondary mt-1">
        <span className="font-medium">Elapsed</span>
        <span className="font-mono text-text-primary bg-bg-elevated px-2 py-0.5 rounded border border-border-subtle">
          {elapsedSeconds.toFixed(1)}s
        </span>
      </div>
    </div>
  );
}
