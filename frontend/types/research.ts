export type SearchMode = "default" | "scholar_only";

export type JobStatus = "queued" | "running" | "completed" | "failed";

export interface ResearchRequest {
  topic: string;
  search_mode: SearchMode;
  year_span?: number;
  academic_quota?: number;
}

export interface ResearchSubmitResponse {
  job_id: string;
  status: JobStatus;
  created_at: string;
}

export interface ResearchStatus {
  job_id: string;
  status: JobStatus;
  stage: string;
  stage_index: number;
  papers_discovered: number;
  elapsed_seconds: number;
  error: string | null;
}

export interface PaperSummary {
  title: string;
  source: "scholar" | "web";
  publication_year?: number | string;
  authors?: string;
  url: string;
  relevance_note?: string;
}

export interface ExtractedContext {
  url: string;
  content_summary?: string;
  key_points?: string[];
  methodology?: string;
}

export interface EvaluationData {
  overall_score: number;
  verdict: string;
  relevance_score: number;
  coverage_score: number;
  synthesis_score: number;
  citation_score: number;
  strengths: string[];
  weaknesses: string[];
  improvement_suggestions?: string[];
  error?: string;
}

export interface ResearchResult {
  draft_report: string;
  evaluation: EvaluationData;
  discovered_papers: PaperSummary[];
  extracted_contexts: ExtractedContext[];
  recommended_reading?: string[];
  extraction_errors: string[];
  search_queries: string[];
  scholar_papers?: any[];
  web_papers?: any[];
  retry_count?: number;
  error_log?: string[];
  discovery_raw?: string;
  search_mode?: string;
}

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    detail: any;
  };
}
