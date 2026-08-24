const API_BASE_URL = (import.meta as ImportMeta & { env: { VITE_API_BASE_URL?: string } }).env
  .VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const TOKEN_STORAGE_KEY = "mip_access_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function setToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // response wasn't JSON -- keep statusText
    }
    throw new ApiError(response.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return response.json() as Promise<T>;
}

export const api = {
  // auth
  register: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string; token_type: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<{ id: number; email: string }>("/api/auth/me"),
  disclaimer: () => request<{ disclaimer: string }>("/api/auth/disclaimer"),

  // data
  marketAnalysis: (asset: string, timeframe: string, limit = 200) =>
    request(`/api/market-analysis/${asset}/${timeframe}?limit=${limit}`),
  predictions: (asset: string, timeframe: string) => request(`/api/predictions/${asset}/${timeframe}`),
  explainability: (asset: string, timeframe: string, model: string) =>
    request(`/api/explainability/${asset}/${timeframe}/${model}`),
  modelLab: (asset: string, timeframe: string) => request(`/api/model-lab/${asset}/${timeframe}`),
  walkForward: (asset: string, timeframe: string) => request(`/api/walk-forward/${asset}/${timeframe}`),
  backtest: (asset: string, timeframe: string, model: string) =>
    request(`/api/backtesting/${asset}/${timeframe}/${model}`),
  performanceByRegime: (asset: string, timeframe: string, model: string) =>
    request(`/api/backtesting/${asset}/${timeframe}/${model}/performance-by-regime`),
  newsSentiment: (asset: string, limit = 100) => request(`/api/news-sentiment/${asset}?limit=${limit}`),
};

export { API_BASE_URL };
