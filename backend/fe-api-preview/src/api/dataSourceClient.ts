import { appConfig } from "../config/appConfig";

export type DataSourceKind = "server" | "local";

export interface DataSourceEvent {
  at: string;
  key: string;
  path: string;
  source: DataSourceKind;
  status?: number;
  message?: string;
}

declare global {
  interface Window {
    __QUANTAGENT_DATA_SOURCES__?: DataSourceEvent[];
  }
}

const DATA_SOURCE_EVENT = "quantagent:data-source";
const MAX_EVENTS = 50;

export function recordDataSource(event: Omit<DataSourceEvent, "at">) {
  const next: DataSourceEvent = { ...event, at: new Date().toISOString() };
  window.__QUANTAGENT_DATA_SOURCES__ = [next, ...(window.__QUANTAGENT_DATA_SOURCES__ ?? [])].slice(0, MAX_EVENTS);
  window.dispatchEvent(new CustomEvent(DATA_SOURCE_EVENT, { detail: next }));

  const prefix = next.source === "server" ? "✅ SERVER" : "⚠️ LOCAL";
  console.info(`[QuantAgent data] ${prefix} ${next.key} ${next.path}`, next);
}

export function getDataSourceEvents() {
  return window.__QUANTAGENT_DATA_SOURCES__ ?? [];
}

export function subscribeDataSourceEvents(listener: () => void) {
  window.addEventListener(DATA_SOURCE_EVENT, listener);
  return () => window.removeEventListener(DATA_SOURCE_EVENT, listener);
}

export async function fetchServerJson<T>({
  key,
  path,
  init,
}: {
  key: string;
  path: string;
  init?: RequestInit;
}): Promise<T> {
  if (!appConfig.backendApiBaseUrl) {
    throw new Error("VITE_BACKEND_API_BASE_URL 설정이 필요합니다.");
  }

  try {
    const response = await fetch(`${appConfig.backendApiBaseUrl}${path}`, {
      credentials: "include",
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
    if (!response.ok) {
      recordDataSource({ key, path, source: "server", status: response.status, message: `HTTP ${response.status}` });
      throw new Error(`Backend API 응답 실패: ${response.status}`);
    }
    recordDataSource({ key, path, source: "server", status: response.status });
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof Error && !error.message.startsWith("Backend API 응답 실패")) {
      recordDataSource({ key, path, source: "server", message: error.message });
    }
    throw error;
  }
}
