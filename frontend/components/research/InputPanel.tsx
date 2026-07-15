"use client";

import React, { useState } from "react";
import { SearchMode } from "../../types/research";

interface InputPanelProps {
  status: string;
  onSubmit: (
    topic: string,
    searchMode: SearchMode,
    yearSpan?: number,
    academicQuota?: number
  ) => void;
  onReset: () => void;
}

export function InputPanel({ status, onSubmit, onReset }: InputPanelProps) {
  const [topic, setTopic] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("default");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [yearSpan, setYearSpan] = useState<number>(5);
  const [academicQuota, setAcademicQuota] = useState<number>(5);

  const isRunning = status === "queued" || status === "running";

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!topic.trim()) return;
    onSubmit(
      topic.trim(),
      searchMode,
      showAdvanced ? yearSpan : undefined,
      showAdvanced ? academicQuota : undefined
    );
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 animate-fade-in-up">
      {/* Topic Input */}
      <div>
        <label className="block mb-2 text-[0.65rem] font-bold uppercase tracking-wider text-text-muted">
          Research Topic
        </label>
        <input
          type="text"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          disabled={isRunning}
          placeholder="e.g. CRISPR gene editing in oncology"
          className="w-full h-11 px-4 text-sm bg-bg-input text-text-primary placeholder:text-text-muted border border-border-default rounded-md focus:outline-none focus:border-accent hover:border-border-hover transition-colors disabled:opacity-50"
          required
        />
      </div>

      {/* Search Strategy */}
      <div>
        <label className="block mb-2 text-[0.65rem] font-bold uppercase tracking-wider text-text-muted">
          Search Strategy
        </label>
        <div className="relative">
          <select
            value={searchMode}
            onChange={(e) => setSearchMode(e.target.value as SearchMode)}
            disabled={isRunning}
            className="w-full h-11 px-4 text-sm bg-bg-input text-text-primary border border-border-default rounded-md appearance-none focus:outline-none focus:border-accent hover:border-border-hover transition-colors disabled:opacity-50 cursor-pointer"
          >
            <option value="default">Mixed Sources (Scholar + Web)</option>
            <option value="scholar_only">Google Scholar Only</option>
          </select>
          <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-text-secondary">
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </div>
        </div>
      </div>

      {/* Advanced Settings Toggle */}
      <div>
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          disabled={isRunning}
          className="text-[0.65rem] font-semibold text-text-tertiary hover:text-accent flex items-center gap-1 transition-colors focus:outline-none disabled:opacity-50"
        >
          <span>{showAdvanced ? "▼ Hide Settings" : "▶ Advanced Constraints"}</span>
        </button>

        {showAdvanced && (
          <div className="mt-3 p-3 bg-bg-card/50 border border-border-subtle rounded-md flex flex-col gap-3">
            <div>
              <label className="block mb-1 text-[0.6rem] font-semibold text-text-tertiary">
                Year Span: {yearSpan} years
              </label>
              <input
                type="range"
                min="1"
                max="20"
                value={yearSpan}
                onChange={(e) => setYearSpan(parseInt(e.target.value))}
                disabled={isRunning}
                className="w-full accent-accent bg-bg-input rounded-lg appearance-none cursor-pointer"
              />
            </div>
            <div>
              <label className="block mb-1 text-[0.6rem] font-semibold text-text-tertiary">
                Paper Quota: {academicQuota} papers
              </label>
              <input
                type="range"
                min="1"
                max="15"
                value={academicQuota}
                onChange={(e) => setAcademicQuota(parseInt(e.target.value))}
                disabled={isRunning}
                className="w-full accent-accent bg-bg-input rounded-lg appearance-none cursor-pointer"
              />
            </div>
          </div>
        )}
      </div>

      {/* Action Buttons */}
      <div className="flex gap-2 mt-2">
        <button
          type="submit"
          disabled={isRunning || !topic.trim()}
          className="flex-1 h-11 bg-accent text-white font-medium text-sm rounded-md shadow-lg shadow-accent-dim hover:bg-accent-light active:translate-y-[1px] disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none transition-all flex items-center justify-center gap-2"
        >
          {isRunning ? (
            <>
              <svg
                className="animate-spin h-4 w-4 text-white"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                ></circle>
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                ></path>
              </svg>
              <span>Researching…</span>
            </>
          ) : (
            <>
              <span>Run Research</span>
              <span>→</span>
            </>
          )}
        </button>

        {!isRunning && status !== "idle" && (
          <button
            type="button"
            onClick={() => {
              setTopic("");
              onReset();
            }}
            className="px-3 border border-border-default text-text-secondary hover:bg-bg-card rounded-md transition-colors text-sm"
          >
            Clear
          </button>
        )}
      </div>
    </form>
  );
}
