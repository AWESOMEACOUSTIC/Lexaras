import {
  ResearchRequest,
  ResearchSubmitResponse,
  ResearchStatus,
  ResearchResult,
  ErrorEnvelope
} from "../types/research";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

class ApiError extends Error {
  code?: string;
  detail?: any;
  status: number;

  constructor(message: string, status: number, code?: string, detail?: any) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const headers = new Headers(options.headers);
  
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  
  if (API_KEY) {
    headers.set("X-API-Key", API_KEY);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorData: ErrorEnvelope | null = null;
    try {
      errorData = await response.json();
    } catch {
      // Not JSON or empty body
    }

    const message = errorData?.error?.message || `HTTP error! status: ${response.status}`;
    const code = errorData?.error?.code || "http_error";
    const detail = errorData?.error?.detail || null;

    throw new ApiError(message, response.status, code, detail);
  }

  return response.json() as Promise<T>;
}

export const apiService = {
  /**
   * Submit a new research topic to the pipeline.
   */
  async submitResearch(req: ResearchRequest): Promise<ResearchSubmitResponse> {
    return request<ResearchSubmitResponse>("/api/v1/research", {
      method: "POST",
      body: JSON.stringify(req),
    });
  },

  /**
   * Get the current execution status and stage of a research job.
   */
  async getResearchStatus(jobId: string): Promise<ResearchStatus> {
    return request<ResearchStatus>(`/api/v1/research/${jobId}`, {
      method: "GET",
    });
  },

  /**
   * Fetch the final research report and evaluation scores.
   * Will return 409 Conflict if the job is still running.
   */
  async getResearchResult(jobId: string): Promise<ResearchResult> {
    return request<ResearchResult>(`/api/v1/research/${jobId}/result`, {
      method: "GET",
    });
  },

  /**
   * Liveness and readiness check.
   */
  async checkHealth(): Promise<{ status: string }> {
    return request<{ status: string }>("/api/v1/health", {
      method: "GET",
    });
  }
};
