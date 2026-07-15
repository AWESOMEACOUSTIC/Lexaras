"use client";

import React from "react";

export function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center p-8 border border-dashed border-border-default bg-bg-card/25 rounded-2xl animate-fade-in-up">
      {/* Premium glowing icon */}
      <div className="relative w-16 h-16 rounded-full border border-border-default flex items-center justify-center text-2xl text-accent shadow-lg shadow-accent-glow bg-bg-card mb-6 group select-none">
        <div className="absolute inset-0 rounded-full border border-accent/20 animate-ping group-hover:duration-500 opacity-60" />
        ◈
      </div>

      <h2 className="text-lg font-bold tracking-tight text-white mb-2">
        Ready to research
      </h2>

      <p className="max-w-md text-xs leading-relaxed text-text-secondary">
        Enter any academic, biomedical, or technical topic in the left panel.
        Lexaras will orchestrate AI agents to discover relevant papers, extract key contexts,
        synthesize a structured report, and score its academic quality end to end.
      </p>
    </div>
  );
}
