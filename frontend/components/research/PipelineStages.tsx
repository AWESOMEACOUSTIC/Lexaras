"use client";

import React from "react";
import { JobStatus } from "../../types/research";

interface PipelineStagesProps {
  status: JobStatus | "idle";
  stageIndex: number;
}

const STAGES = [
  { icon: "🔍", name: "Discovery", description: "Generating queries · Searching the web" },
  { icon: "📖", name: "Extraction", description: "Reading papers · Pulling key context" },
  { icon: "✍️", name: "Writing", description: "Synthesising report across all sources" },
  { icon: "🧪", name: "Evaluation", description: "Scoring relevance, coverage & quality" },
];

export function PipelineStages({ status, stageIndex }: PipelineStagesProps) {
  const isFailed = status === "failed";
  const isQueued = status === "queued";
  const isIdle = status === "idle";

  return (
    <div className="flex flex-col gap-1 select-none animate-fade-in-up">
      <label className="block mb-2 text-[0.65rem] font-bold uppercase tracking-wider text-text-muted">
        Pipeline
      </label>
      <div className="relative pl-6 flex flex-col gap-5">
        {/* Connecting timeline line */}
        <div className="absolute top-3 bottom-3 left-[9px] w-[2px] bg-border-subtle" />

        {STAGES.map((stg, i) => {
          let state: "done" | "active" | "error" | "idle" = "idle";
          let statusText = stg.description;

          if (isIdle) {
            state = "idle";
          } else if (i < stageIndex) {
            state = "done";
            statusText = "Complete";
          } else if (i === stageIndex) {
            if (isFailed) {
              state = "error";
              statusText = "Error";
            } else if (isQueued) {
              state = "active";
              statusText = "Queued…";
            } else {
              state = "active";
              statusText = "Running…";
            }
          } else {
            state = "idle";
          }

          // Styles mapping
          const circleStyles = {
            done: "bg-green-dim border-green-light text-green-light shadow-md shadow-green-dim",
            active: "bg-accent-dim border-accent-light text-accent-light animate-pulse shadow-md shadow-accent-dim",
            error: "bg-red-dim border-red-light text-red-light shadow-md shadow-red-dim",
            idle: "bg-bg-input border-border-default text-text-muted",
          }[state];

          const lineFillStyles = {
            done: "bg-green-light",
            active: "bg-accent-light animate-pulse",
            error: "bg-red-light",
            idle: "bg-transparent",
          }[state];

          const textStyles = {
            done: "text-text-secondary font-medium",
            active: "text-white font-semibold",
            error: "text-red-light font-medium",
            idle: "text-text-muted",
          }[state];

          const subTextStyles = {
            done: "text-green-light/80 font-medium",
            active: "text-accent-light animate-pulse font-medium",
            error: "text-red-light/80 font-medium",
            idle: "text-text-muted/60",
          }[state];

          return (
            <div key={stg.name} className="relative flex items-start gap-4">
              {/* Dynamic portion of the timeline line */}
              {i > 0 && i <= stageIndex && (
                <div
                  className={`absolute -top-6 left-[-17px] w-[2px] h-6 ${lineFillStyles}`}
                />
              )}

              {/* Step indicator circle */}
              <div
                className={`absolute left-[-23px] top-1.5 w-5 h-5 rounded-full border flex items-center justify-center text-[10px] z-10 transition-all ${circleStyles}`}
              >
                {state === "done" ? (
                  <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                  </svg>
                ) : state === "error" ? (
                  <span>!</span>
                ) : (
                  <span>{i + 1}</span>
                )}
              </div>

              {/* Stage content */}
              <div className="flex-1 flex flex-col min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className={`text-xs ${textStyles}`}>{stg.name}</span>
                  <span className="text-[14px]">{stg.icon}</span>
                </div>
                <span className={`text-[10px] mt-0.5 leading-normal ${subTextStyles}`}>
                  {statusText}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
