"use client";

import React, { useState } from "react";
import { Header } from "../components/research/Header";
import { InputPanel } from "../components/research/InputPanel";
import { PipelineStages } from "../components/research/PipelineStages";
import { RunStats } from "../components/research/RunStats";
import { EmptyState } from "../components/research/EmptyState";
import { OutputTabs } from "../components/research/OutputTabs";
import { useResearch } from "../hooks/useResearch";
import { SearchMode } from "../types/research";

export default function Home() {
  const {
    status,
    stage,
    stageIndex,
    papersDiscovered,
    elapsedSeconds,
    error,
    result,
    startResearch,
    reset,
  } = useResearch();

  const [lastSubmittedTopic, setLastSubmittedTopic] = useState("");

  const handleSubmit = (
    topic: string,
    searchMode: SearchMode,
    yearSpan?: number,
    academicQuota?: number
  ) => {
    setLastSubmittedTopic(topic);
    startResearch(topic, searchMode, yearSpan, academicQuota);
  };

  const isRunning = status === "queued" || status === "running";

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 h-screen w-full overflow-hidden bg-bg-deep text-text-secondary font-sans antialiased">
      {/* ── LEFT PANEL (Inputs & Controls) ── */}
      <aside className="lg:col-span-5 xl:col-span-4 h-full overflow-y-auto border-r border-border-subtle bg-bg-deep px-6 py-8 flex flex-col gap-6 select-none scrollbar-thin">
        <Header />
        
        <InputPanel
          status={status}
          onSubmit={handleSubmit}
          onReset={reset}
        />
        
        <hr className="border-border-subtle" />
        
        <PipelineStages
          status={status}
          stageIndex={stageIndex}
        />
        
        <hr className="border-border-subtle" />
        
        <RunStats
          result={result}
          papersDiscovered={papersDiscovered}
          elapsedSeconds={elapsedSeconds}
        />
      </aside>

      {/* ── RIGHT PANEL (Output Results Viewport) ── */}
      <main className="lg:col-span-7 xl:col-span-8 h-full overflow-y-auto bg-bg-base px-6 py-8 md:px-10 lg:px-12 scroll-behavior-smooth">
        {status === "idle" && <EmptyState />}

        {/* Polling / Execution Progress View */}
        {isRunning && (
          <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-8 border border-border-subtle bg-bg-card/30 rounded-2xl animate-fade-in-up select-none">
            {/* Pulsing loading sphere */}
            <div className="relative w-16 h-16 rounded-full border border-accent/25 flex items-center justify-center bg-bg-card mb-6 shadow-lg shadow-accent-glow">
              <div className="absolute inset-0 rounded-full border-2 border-accent border-t-transparent animate-spin" />
              <div className="absolute inset-2 rounded-full bg-accent-dim/30 animate-pulse" />
              <span className="text-xs">◈</span>
            </div>

            <h3 className="text-sm font-bold text-white mb-1 uppercase tracking-wider">
              {stage ? `${stage} Stage` : "Initializing Pipeline"}
            </h3>
            
            <p className="text-xs text-text-secondary max-w-sm mb-4 leading-normal">
              {stageIndex === 0 && "Discovering and selecting scholarly literature on the web…"}
              {stageIndex === 1 && `Reading discovered sources and extracting key context (${papersDiscovered} papers found)…`}
              {stageIndex === 2 && "Synthesizing research notes into structured markdown sections…"}
              {stageIndex === 3 && "Evaluating synthesized drafts against academic rigor and schema rules…"}
            </p>

            {/* Micro loading progress animation */}
            <div className="w-48 h-1 bg-border-subtle rounded-full overflow-hidden relative">
              <div className="absolute top-0 bottom-0 left-0 w-1/3 bg-accent rounded-full animate-shimmer" style={{ animationDuration: '1.5s' }} />
            </div>
            
            <span className="text-[10px] text-text-muted mt-3 font-mono">
              Elapsed time: {elapsedSeconds.toFixed(1)}s
            </span>
          </div>
        )}

        {/* Failure view */}
        {status === "failed" && (
          <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-8 border border-red-custom/10 bg-red-custom/5 rounded-2xl animate-fade-in-up">
            <div className="w-12 h-12 rounded-full bg-red-dim border border-red-light/30 flex items-center justify-center text-red-light text-xl mb-4 font-bold select-none">
              !
            </div>
            
            <h3 className="text-sm font-bold text-white mb-2">
              Research Pipeline Interrupted
            </h3>
            
            <div className="p-4 bg-bg-deep border border-border-subtle rounded-lg text-xs font-mono text-red-light max-w-lg mb-6 break-words leading-relaxed">
              {error || "An unknown exception occurred in the background thread executor."}
            </div>

            <p className="text-xs text-text-secondary max-w-xs mb-6 leading-relaxed">
              Please check your <code>.env</code> file, verify third-party API credentials (Mistral, SerpApi), and confirm your local network connection.
            </p>

            <button
              onClick={reset}
              className="h-10 px-6 text-xs font-semibold bg-bg-elevated border border-border-default text-white hover:text-accent hover:border-accent rounded-md transition-colors select-none"
            >
              Configure and Try Again
            </button>
          </div>
        )}

        {/* Results tab view */}
        {status === "completed" && result && (
          <OutputTabs
            result={result}
            topicLabel={lastSubmittedTopic}
          />
        )}
      </main>
    </div>
  );
}
