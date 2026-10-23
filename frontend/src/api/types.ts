// Core API types for MudaleTunnel control plane.
// Mirrors the DRF API contract at /api/v1.

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface HealthResponse {
  status: string;
}

export interface EngineInstance {
  instance_id: string;
  hostname: string;
  version: string;
  /** What this engine can drive, keyed by capability name. The backend sends
   *  an object, not a list, so an unavailable capability is reported as
   *  `false` rather than simply being absent. */
  capabilities: Record<string, boolean>;
  last_heartbeat_at: string | null;
}

export interface EngineStatus {
  attached: boolean;
  instances: EngineInstance[];
}

export type EngagementStatus = 'planned' | 'active' | 'paused' | 'closed';

export interface Engagement {
  id: number;
  name: string;
  slug: string;
  client: string;
  status: EngagementStatus;
  authorized_cidrs: string[];
  starts_on: string | null;
  ends_on: string | null;
  notes: string;
  created_at: string;
  tunnel_count: number;
  scan_count: number;
  agent_count: number;
}

export type EngagementWritePayload = Partial<
  Pick<
    Engagement,
    'name' | 'client' | 'status' | 'authorized_cidrs' | 'starts_on' | 'ends_on' | 'notes'
  >
>;

export type AgentEngine = 'ssh';
export type AgentStatus = 'pending' | 'online' | 'offline' | 'retired';

export interface Agent {
  id: number;
  engagement: number;
  engine: AgentEngine;
  name: string;
  status: AgentStatus;
  remote_host: string;
  remote_port: number;
  hostname: string;
  operating_system: string;
  architecture: string;
  remote_username: string;
  is_privileged: boolean;
  reachable_cidrs: string[];
  last_seen_at: string | null;
  created_at: string;
}

export type AgentWritePayload = Partial<
  Pick<
    Agent,
    | 'engagement'
    | 'engine'
    | 'name'
    | 'status'
    | 'remote_host'
    | 'remote_port'
    | 'remote_username'
    | 'is_privileged'
  >
>;

export type TunnelKind = 'ssh_local' | 'ssh_dynamic' | 'ssh_remote' | 'ssh_remote_dynamic' | 'ligolo';

export type TunnelDesiredState = 'up' | 'down';

export type TunnelStatus =
  | 'pending'
  | 'starting'
  | 'active'
  | 'degraded'
  | 'stopping'
  | 'stopped'
  | 'failed';

export interface Tunnel {
  id: number;
  engagement: number;
  engagement_name: string;
  agent: number | null;
  agent_name: string | null;
  kind: TunnelKind;
  kind_display: string;
  label: string;
  description: string;
  desired_state: TunnelDesiredState;
  status: TunnelStatus;
  spec: Record<string, unknown>;
  pid: number | null;
  last_error: string;
  restart_count: number;
  started_at: string | null;
  stopped_at: string | null;
  created_at: string;
  created_by_name: string;
  uptime_seconds: number | null;
}

export interface TunnelCreatePayload {
  engagement: number;
  kind: TunnelKind;
  label: string;
  spec: Record<string, unknown>;
  agent?: number;
  description?: string;
}

export type LogLevel = 'debug' | 'info' | 'warning' | 'error' | 'critical';

export interface TunnelLog {
  id: number;
  created_at: string;
  level: LogLevel | string;
  message: string;
  source: string;
}

export type ScanStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled'
  | 'timed_out';

export type ScanProfile = 'discovery' | 'quick' | 'standard' | 'full' | 'udp_top';

export interface Scan {
  id: number;
  engagement: number;
  target: string;
  profile: ScanProfile;
  profile_display: string;
  status: ScanStatus;
  via_tunnel: number | null;
  hosts_up: number | null;
  services_found: number | null;
  error: string;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  requested_by_name: string;
}

export interface ScanCreatePayload {
  engagement: number;
  target: string;
  profile: ScanProfile;
  via_tunnel?: number;
}

export interface Service {
  id: number;
  host: string;
  hostname: string;
  port: number;
  protocol: string;
  state: string;
  service_name: string;
  product: string;
  version: string;
  extra_info: string;
  banner: string;
  scan?: number;
  target?: string;
}

// Pivot map — reachability discovered by scanning through SOCKS pivots (SSH -D),
// not assumed from a routed subnet. Evidence, not assumption.

export interface ReachableHost {
  host: string;
  hostname: string;
  open_ports: number[];
}

export interface PivotEntry {
  tunnel: number;
  label: string;
  subnets: string[];
  hosts: ReachableHost[];
}

export interface PivotMap {
  engagement: number;
  total_hosts: number;
  direct: ReachableHost[];
  pivots: PivotEntry[];
}

export interface ReachableResponse {
  tunnel: number;
  subnets: string[];
  hosts: ReachableHost[];
}

export interface ProxychainsConfig {
  config: string;
}

export interface AutoExposeResponse {
  created: Tunnel[];
  count: number;
}

export type AuditResult = 'success' | 'denied' | 'error';

export interface AuditEvent {
  id: number;
  created_at: string;
  actor_label: string;
  action: string;
  action_display: string;
  result: AuditResult | string;
  engagement: number | null;
  object_type: string;
  object_id: number | string | null;
  object_label: string;
  message: string;
  request_id: string;
  source_ip: string;
}

export type UserRole = 'admin' | 'operator' | 'viewer';

export interface Me {
  /** Server version, shown in the sidebar so a screenshot or bug report always
   *  says which build it came from. Authenticated — /health/ deliberately does
   *  not disclose it. */
  server_version: string;
  id: number;
  username: string;
  callsign: string;
  role: UserRole;
  can_mutate: boolean;
  is_admin: boolean;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface ApiErrorShape {
  detail?: string;
  [field: string]: unknown;
}

// WebSocket message types

export interface WsTunnelUpdated {
  type: 'tunnel.updated';
  tunnel: Tunnel;
}

export interface WsTunnelLog {
  type: 'tunnel.log';
  tunnel_id: number;
  log: TunnelLog;
}

export interface WsScanUpdated {
  type: 'scan.updated';
  scan: Scan;
}

export interface WsAgentUpdated {
  type: 'agent.updated';
  agent: Agent;
}

export interface WsEngineStatus {
  type: 'engine.status';
  attached: boolean;
}

export interface WsPong {
  type: 'pong';
}

export type WsMessage =
  | WsTunnelUpdated
  | WsTunnelLog
  | WsScanUpdated
  | WsAgentUpdated
  | WsEngineStatus
  | WsPong;

export interface DemoCredentials {
  username: string;
  password: string;
}

export interface Bootstrap {
  /** Populated only on a loopback-only deployment. Null everywhere else. */
  demo_credentials: DemoCredentials | null;
  /** True when credentials were configured but withheld because the
   *  deployment is reachable beyond loopback. */
  demo_suppressed: boolean;
}
