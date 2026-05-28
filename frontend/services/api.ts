import axios from 'axios';

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
});

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Trial {
  id: number;
  nct_id: string;
  title?: string;
  condition?: string;
  drug_name?: string;
  phase?: string;
  overall_status?: string;
  why_stopped?: string;
  failure_category?: string;
  salvageability_score?: number;
  recommended_actions?: string[];
  sponsor?: string;
  start_date?: string;
  completion_date?: string;
  enrollment?: number;
  created_at?: string;
}

export interface TrialListResponse {
  total: number;
  page: number;
  page_size: number;
  results: Trial[];
}

export interface DashboardStats {
  total_trials: number;
  by_status: Record<string, number>;
  by_phase: Record<string, number>;
  by_failure_category: Record<string, number>;
  avg_salvageability: number;
  top_salvageable: Trial[];
}

export interface ClassifyResponse {
  why_stopped: string;
  failure_category: string;
  salvageability_score: number;
  recommended_actions: string[];
}

export interface IngestResponse {
  fetched: number;
  inserted: number;
  skipped: number;
  message: string;
}

export interface TrialFilters {
  page?: number;
  page_size?: number;
  search?: string;
  phase?: string;
  failure_category?: string;
  overall_status?: string;
  min_score?: number;
  max_score?: number;
}

// ─── API Functions ────────────────────────────────────────────────────────────

export const trialsApi = {
  list: async (filters: TrialFilters = {}): Promise<TrialListResponse> => {
    const params = Object.fromEntries(
      Object.entries(filters).filter(([, v]) => v !== undefined && v !== '')
    );
    const { data } = await api.get('/trials/', { params });
    return data;
  },

  getById: async (id: number): Promise<Trial> => {
    const { data } = await api.get(`/trials/${id}`);
    return data;
  },

  getByNct: async (nctId: string): Promise<Trial> => {
    const { data } = await api.get(`/trials/nct/${nctId}`);
    return data;
  },

  getStats: async (): Promise<DashboardStats> => {
    const { data } = await api.get('/trials/stats');
    return data;
  },
};

export const classifyApi = {
  classify: async (whyStopped: string): Promise<ClassifyResponse> => {
    const { data } = await api.post('/classify/', { why_stopped: whyStopped });
    return data;
  },
};

export const ingestApi = {
  trigger: async (params: {
    max_results?: number;
    condition?: string;
    intervention?: string;
  }): Promise<IngestResponse> => {
    const { data } = await api.post('/ingest/', null, { params });
    return data;
  },
};

export default api;
