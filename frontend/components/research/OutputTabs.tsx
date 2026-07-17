"use client";

import React, { useState } from "react";
import { ResearchResult } from "../../types/research";
import { ReportTab } from "./ReportTab";
import { SourcesTab } from "./SourcesTab";
import { EvaluationTab } from "./EvaluationTab";
import { DebugTab } from "./DebugTab";

interface OutputTabsProps {
  result: ResearchResult;
  topicLabel: string;
}

type TabType = "report" | "sources" | "evaluation" | "debug";

export function OutputTabs({ result, topicLabel }: OutputTabsProps) {
  const [activeTab, setActiveTab] = useState<TabType>("report");
  const extractionErrors = result.extraction_errors || [];
  const searchMode = result.search_mode || "default";

  const tabs = [
    { id: "report", label: "📄 Report" },
    { id: "sources", label: "📚 Sources" },
    { id: "evaluation", label: "🧪 Evaluation" },
    { id: "debug", label: "🔧 Debug" },
  ] as const;

  return (
    <div className="flex flex-col gap-4 animate-fade-in-up">
      {/* 1. Header Card */}
      <div className="p-5 bg-bg-card border-t-2 border-t-accent border-x border-b border-border-subtle rounded-xl flex flex-col gap-2.5">
        <div className="text-[10px] font-bold text-text-muted uppercase tracking-wider">
          Research Output For
        </div>
        <h2 className="text-base font-bold text-white leading-normal">
          {topicLabel}
        </h2>
        <div className="flex flex-wrap gap-1.5 mt-1 select-none">
          <span className="text-[9px] px-2 py-0.5 font-semibold bg-bg-elevated border border-border-subtle text-text-secondary rounded-full">
            Mode: {searchMode === "scholar_only" ? "Scholar Only" : "Mixed Sources"}
          </span>
        </div>
      </div>

      {/* 2. Extraction Error Warning Banner */}
      {extractionErrors.length > 0 && (
        <div className="p-3 bg-amber-custom/5 border border-amber-custom/15 text-amber-light text-xs rounded-lg flex items-center gap-2">
          <span>⚠</span>
          <span>
            {extractionErrors.length} paper(s) failed to extract. See the Debug tab for exceptions.
          </span>
        </div>
      )}

      {/* 3. Custom Tab Buttons */}
      <div className="flex border-b border-border-subtle gap-2 overflow-x-auto pb-px select-none">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`h-9 px-4 text-xs font-semibold whitespace-nowrap border-b-2 transition-all duration-300 focus:outline-none ${
                isActive
                  ? "border-accent text-accent shadow-sm"
                  : "border-transparent text-text-secondary hover:text-white"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* 4. Tab Views Viewport */}
      <div className="mt-2">
        {activeTab === "report" && <ReportTab result={result} topicLabel={topicLabel} />}
        {activeTab === "sources" && <SourcesTab result={result} />}
        {activeTab === "evaluation" && <EvaluationTab result={result} />}
        {activeTab === "debug" && <DebugTab result={result} />}
      </div>
    </div>
  );
}
