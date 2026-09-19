// Thin fetch wrapper. Keeps auth-token handling and error shaping in one
// place so every page calls the same small surface.

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

function token(): string | null {
  return localStorage.getItem("civicpulse.token");
}

export function setToken(t: string | null) {
  if (t) localStorage.setItem("civicpulse.token", t);
  else localStorage.removeItem("civicpulse.token");
}

async function request<T>(
  path: string,
  opts: { method?: string; body?: unknown; params?: Record<string, unknown>; formData?: FormData } = {},
): Promise<T> {
  const url = new URL(path.startsWith("http") ? path : BASE_URL + path);
  if (opts.params) {
    for (const [k, v] of Object.entries(opts.params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  const headers: Record<string, string> = {};
  const t = token();
  if (t) headers.Authorization = `Bearer ${t}`;
  let body: BodyInit | undefined;
  if (opts.formData) {
    body = opts.formData;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  let res: Response;
  try {
    res = await fetch(url.toString(), { method: opts.method || "GET", headers, body });
  } catch {
    throw new ApiError(0, "Network unreachable. Check that the backend is running.");
  }

  if (res.status === 204) return undefined as T;
  const isJson = res.headers.get("content-type")?.includes("application/json");
  const data = isJson ? await res.json().catch(() => null) : null;

  if (!res.ok) {
    const message =
      (data && typeof data === "object" && "detail" in data && typeof (data as { detail: unknown }).detail === "string"
        ? (data as { detail: string }).detail
        : null) || `Request failed (${res.status})`;
    throw new ApiError(res.status, message, data);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, unknown>) => request<T>(path, { params }),
  post: <T>(path: string, body?: unknown, params?: Record<string, unknown>) =>
    request<T>(path, { method: "POST", body, params }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
  delete: <T>(path: string, params?: Record<string, unknown>) =>
    request<T>(path, { method: "DELETE", params }),
  upload: <T>(path: string, formData: FormData, params?: Record<string, unknown>) =>
    request<T>(path, { method: "POST", formData, params }),
};

export { BASE_URL };
