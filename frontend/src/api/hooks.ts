import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from './client';
import type {
  Agent,
  AgentWritePayload,
  AuditEvent,
  Engagement,
  EngagementWritePayload,
  EngineStatus,
  HealthResponse,
  Listener,
  Me,
  Paginated,
  Route,
  Scan,
  ScanCreatePayload,
  Service,
  Tunnel,
  TunnelCreatePayload,
  TunnelLog,
} from './types';

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | Error | null;
}

type QueryParams = Record<string, string | number | boolean | undefined | null>;

/** Generic list-fetch hook against a paginated endpoint, re-fetched when deps change. */
function useList<T>(path: string | null, query?: QueryParams) {
  const [state, setState] = useState<AsyncState<Paginated<T>>>({
    data: null,
    loading: true,
    error: null,
  });
  const queryKey = JSON.stringify(query ?? {});
  const reloadToken = useRef(0);

  const reload = useCallback(() => {
    reloadToken.current += 1;
    setState((s) => ({ ...s, loading: true }));
  }, []);

  useEffect(() => {
    if (!path) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    api
      .get<Paginated<T>>(path, query, controller.signal)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ data: null, loading: false, error: error as ApiError });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, queryKey, reloadToken.current]);

  return {
    items: state.data?.results ?? [],
    count: state.data?.count ?? 0,
    loading: state.loading,
    error: state.error,
    reload,
  };
}

function useItem<T>(path: string | null) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null });
  const reloadToken = useRef(0);

  const reload = useCallback(() => {
    reloadToken.current += 1;
    setState((s) => ({ ...s, loading: true }));
  }, []);

  useEffect(() => {
    if (!path) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    api
      .get<T>(path, undefined, controller.signal)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setState({ data: null, loading: false, error: error as ApiError });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, reloadToken.current]);

  return { data: state.data, loading: state.loading, error: state.error, reload, setState };
}

export function useHealth() {
  return useItem<HealthResponse>('/health/');
}

export function useMe() {
  return useItem<Me>('/me/');
}

export function useEngineStatus() {
  return useItem<EngineStatus>('/engine/status/');
}

export function useEngagements() {
  return useList<Engagement>('/engagements/');
}

export function useEngagement(id: number | null) {
  return useItem<Engagement>(id ? `/engagements/${id}/` : null);
}

export async function createEngagement(payload: EngagementWritePayload & { name: string }) {
  return api.post<Engagement>('/engagements/', payload);
}

export async function updateEngagement(id: number, payload: EngagementWritePayload) {
  return api.patch<Engagement>(`/engagements/${id}/`, payload);
}

export async function deleteEngagement(id: number) {
  return api.delete<void>(`/engagements/${id}/`);
}

export function useAgents(engagementId?: number | null) {
  return useList<Agent>('/agents/', { engagement: engagementId ?? undefined });
}

export async function createAgent(payload: AgentWritePayload) {
  return api.post<Agent>('/agents/', payload);
}

export async function updateAgent(id: number, payload: AgentWritePayload) {
  return api.patch<Agent>(`/agents/${id}/`, payload);
}

export async function deleteAgent(id: number) {
  return api.delete<void>(`/agents/${id}/`);
}

export function useTunnels(filters: { engagement?: number | null; status?: string | null }) {
  return useList<Tunnel>('/tunnels/', {
    engagement: filters.engagement ?? undefined,
    status: filters.status ?? undefined,
  });
}

export function useTunnel(id: number | null) {
  return useItem<Tunnel>(id ? `/tunnels/${id}/` : null);
}

export async function createTunnel(payload: TunnelCreatePayload) {
  return api.post<Tunnel>('/tunnels/', payload);
}

export async function deleteTunnel(id: number) {
  return api.delete<void>(`/tunnels/${id}/`);
}

export async function stopTunnel(id: number) {
  return api.post<Tunnel>(`/tunnels/${id}/stop/`);
}

export async function startTunnel(id: number) {
  return api.post<Tunnel>(`/tunnels/${id}/start/`);
}

export async function fetchTunnelLogs(id: number, limit = 200) {
  return api.get<{ results: TunnelLog[] }>(`/tunnels/${id}/logs/`, { limit });
}

export async function addRoute(tunnelId: number, cidr: string) {
  return api.post<Route>(`/tunnels/${tunnelId}/routes/`, { cidr });
}

export async function deleteRoute(routeId: number) {
  return api.delete<void>(`/routes/${routeId}/`);
}

export interface ListenerPayload {
  bind_host: string;
  bind_port: number;
  to_host: string;
  to_port: number;
  protocol: string;
  label: string;
}

export async function addListener(tunnelId: number, payload: ListenerPayload) {
  return api.post<Listener>(`/tunnels/${tunnelId}/listeners/`, payload);
}

export async function deleteListener(listenerId: number) {
  return api.delete<void>(`/listeners/${listenerId}/`);
}

export function useScans(engagementId?: number | null) {
  return useList<Scan>('/scans/', { engagement: engagementId ?? undefined });
}

export async function createScan(payload: ScanCreatePayload) {
  return api.post<Scan>('/scans/', payload);
}

export async function deleteScan(id: number) {
  return api.delete<void>(`/scans/${id}/`);
}

export function useScanServices(scanId: number | null) {
  return useList<Service>(scanId ? `/scans/${scanId}/services/` : null);
}

export function useServices(engagementId?: number | null) {
  return useList<Service>('/services/', { engagement: engagementId ?? undefined });
}

export function useAudit(filters: {
  engagement?: number | null;
  action?: string | null;
  result?: string | null;
}) {
  return useList<AuditEvent>('/audit/', {
    engagement: filters.engagement ?? undefined,
    action: filters.action ?? undefined,
    result: filters.result ?? undefined,
  });
}

export async function login(username: string, password: string) {
  return api.post<Me>('/auth/login/', { username, password });
}

export async function logout() {
  return api.post<void>('/auth/logout/');
}
