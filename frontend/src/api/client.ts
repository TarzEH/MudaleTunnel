// Fetch wrapper for the MudaleTunnel API.
// Handles session-cookie auth + CSRF header, or a Bearer API key stored locally.

const API_BASE = '/api/v1';
const API_KEY_STORAGE_KEY = 'mudaletunnel.apiKey';

export class ApiError extends Error {
  status: number;
  detail: string;
  fieldErrors: Record<string, unknown> | null;

  constructor(status: number, detail: string, fieldErrors: Record<string, unknown> | null = null) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
  }
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match && match[1] ? decodeURIComponent(match[1]) : null;
}

export function getStoredApiKey(): string | null {
  return localStorage.getItem(API_KEY_STORAGE_KEY);
}

export function setStoredApiKey(key: string | null): void {
  if (key) {
    localStorage.setItem(API_KEY_STORAGE_KEY, key);
  } else {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
  }
}

const UNSAFE_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(API_BASE + path, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    }
  }
  return url.pathname + url.search;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };

  const apiKey = getStoredApiKey();
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`;
  }

  if (UNSAFE_METHODS.has(method)) {
    const csrfToken = readCookie('csrftoken');
    if (csrfToken) {
      headers['X-CSRFToken'] = csrfToken;
    }
  }

  let body: BodyInit | undefined;
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(options.body);
  }

  const res = await fetch(buildUrl(path, options.query), {
    method,
    headers,
    body,
    credentials: 'same-origin',
    signal: options.signal,
  });

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get('content-type') ?? '';
  const isJson = contentType.includes('application/json');
  const data = isJson ? await res.json().catch(() => null) : null;

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    let fieldErrors: Record<string, unknown> | null = null;
    if (data && typeof data === 'object') {
      const obj = data as Record<string, unknown>;
      if (typeof obj.detail === 'string') {
        detail = obj.detail;
      } else {
        // DRF field-error shape: { field: ["msg", ...] }
        fieldErrors = obj;
        const firstKey = Object.keys(obj)[0];
        if (firstKey) {
          const val = obj[firstKey];
          const msg = Array.isArray(val) ? val[0] : val;
          detail = `${firstKey}: ${String(msg)}`;
        }
      }
    }
    throw new ApiError(res.status, detail, fieldErrors);
  }

  return (data as T) ?? (undefined as T);
}

export const api = {
  get<T>(path: string, query?: RequestOptions['query'], signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: 'GET', query, signal });
  },
  post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: 'POST', body, signal });
  },
  patch<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: 'PATCH', body, signal });
  },
  delete<T>(path: string, signal?: AbortSignal): Promise<T> {
    return request<T>(path, { method: 'DELETE', signal });
  },
};

export function wsUrl(path: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}${path}`;
}
