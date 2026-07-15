"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { apiService } from "../lib/api";
import {
  SearchMode,
  JobStatus,
  ResearchResult,
  ResearchStatus
} from "../types/research";

export function useResearch() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<JobStatus | "idle">("idle");
  const [stage, setStage] = useState<string>("");
  const [stageIndex, setStageIndex] = useState<number>(-1);
  const [papersDiscovered, setPapersDiscovered] = useState<number>(0);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ResearchResult | null>(null);

  const pollingIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Clean up timers
  const clearTimers = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    if (timerIntervalRef.current) {
      clearInterval(timerIntervalRef.current);
      timerIntervalRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => clearTimers();
  }, [clearTimers]);

  // Reset helper
  const reset = useCallback(() => {
    clearTimers();
    setJobId(null);
    setStatus("idle");
    setStage("");
    setStageIndex(-1);
    setPapersDiscovered(0);
    setElapsedSeconds(0);
    setError(null);
    setResult(null);
  }, [clearTimers]);

  // Polling details loop
  const pollStatus = useCallback(async (id: string) => {
    try {
      const statusData: ResearchStatus = await apiService.getResearchStatus(id);
      
      setStatus(statusData.status);
      setStage(statusData.stage);
      setStageIndex(statusData.stage_index);
      setPapersDiscovered(statusData.papers_discovered);
      // We also update the elapsed from the server to keep it synced
      if (statusData.elapsed_seconds) {
        setElapsedSeconds(statusData.elapsed_seconds);
      }

      if (statusData.status === "completed") {
        clearTimers();
        // Fetch results
        const resultData = await apiService.getResearchResult(id);
        setResult(resultData);
      } else if (statusData.status === "failed") {
        clearTimers();
        setError(statusData.error || "The pipeline failed during execution.");
      }
    } catch (err: any) {
      // Don't kill polling on a transient network failure, but record errors
      console.error("Polling error:", err);
      // If we get consecutive or critical errors we might want to stop
      if (err.status === 404) {
        clearTimers();
        setStatus("failed");
        setError("Job not found on server.");
      }
    }
  }, [clearTimers]);

  // Initiate research run
  const startResearch = useCallback(async (
    topic: string,
    searchMode: SearchMode,
    yearSpan?: number,
    academicQuota?: number
  ) => {
    reset();
    setStatus("queued");
    setStage("Discovery");
    setStageIndex(0);

    const startTime = Date.now();
    
    // Start local timer for high-granularity UI display
    timerIntervalRef.current = setInterval(() => {
      setElapsedSeconds(Math.round((Date.now() - startTime) / 100) / 10);
    }, 100);

    try {
      const submitResponse = await apiService.submitResearch({
        topic,
        search_mode: searchMode,
        year_span: yearSpan,
        academic_quota: academicQuota,
      });

      const newJobId = submitResponse.job_id;
      setJobId(newJobId);
      setStatus(submitResponse.status);

      // Start polling
      pollingIntervalRef.current = setInterval(() => {
        pollStatus(newJobId);
      }, 1500);

      // Call immediate first status check
      await pollStatus(newJobId);
    } catch (err: any) {
      clearTimers();
      setStatus("failed");
      setError(err.message || "Failed to submit research job.");
    }
  }, [reset, clearTimers, pollStatus]);

  return {
    jobId,
    status,
    stage,
    stageIndex,
    papersDiscovered,
    elapsedSeconds,
    error,
    result,
    startResearch,
    reset,
  };
}
