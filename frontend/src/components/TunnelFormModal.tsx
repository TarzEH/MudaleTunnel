import { useEffect, useState } from 'react';
import { createTunnel, useAgents } from '../api/hooks';
import { ApiError } from '../api/client';
import type { TunnelKind } from '../api/types';
import { Button } from './Button';
import { Field, Select, TextInput } from './Form';
import { Modal } from './Modal';

const KIND_OPTIONS: { value: TunnelKind; label: string; hint: string }[] = [
  {
    value: 'ssh_dynamic',
    label: 'SOCKS proxy (-D)',
    hint: 'The pivot. Open this first, then scan through it to discover what it reaches.',
  },
  {
    value: 'ssh_local',
    label: 'Local forward (-L)',
    hint: 'Bring one remote service to a local port.',
  },
  {
    value: 'ssh_remote',
    label: 'Reverse forward (-R)',
    hint: 'Expose one of your local services on the remote side.',
  },
  {
    value: 'ssh_remote_dynamic',
    label: 'Reverse SOCKS (-R)',
    hint: 'Reverse SOCKS. Needs OpenSSH 7.6+ on both ends.',
  },
  {
    value: 'ligolo',
    label: 'ligolo-ng (TUN)',
    hint: 'Full IP-layer pivoting via TUN interface. Needs agent on the target and root on the operator.',
  },
];

/**
 * Which spec fields each kind needs, using the exact names the backend's
 * pydantic schemas expect. These are validated with `extra="forbid"`, so a
 * wrong or invented key is rejected outright rather than silently ignored.
 */
const SPEC_FIELDS: Record<TunnelKind, SpecField[]> = {
  ssh_local: ['local_bind', 'local_port', 'target_host', 'target_port'],
  ssh_dynamic: ['local_bind', 'local_port'],
  ssh_remote: ['remote_bind', 'remote_port', 'target_host', 'target_port'],
  ssh_remote_dynamic: ['remote_bind', 'remote_port'],
  ligolo: ['agent_addr', 'listen_port', 'tun_name', 'laddr'],
};

type SpecField =
  | 'local_bind'
  | 'local_port'
  | 'remote_bind'
  | 'remote_port'
  | 'target_host'
  | 'target_port'
  | 'agent_addr'
  | 'listen_port'
  | 'tun_name'
  | 'laddr';

const FIELD_LABELS: Record<SpecField, string> = {
  local_bind: 'Local bind',
  local_port: 'Local port',
  remote_bind: 'Remote bind',
  remote_port: 'Remote port',
  target_host: 'Target host',
  target_port: 'Target port',
  agent_addr: 'Agent address',
  listen_port: 'Listen port',
  tun_name: 'TUN interface',
  laddr: 'Listen address',
};

const FIELD_HINTS: Partial<Record<SpecField, string>> = {
  local_bind: '127.0.0.1 keeps it on this machine. 0.0.0.0 exposes it to your network.',
  remote_bind: 'Bind address on the remote host. Must be a literal IP.',
  target_host: 'Must be inside the engagement scope.',
  agent_addr: 'IP where the ligolo agent connects from.',
  listen_port: 'Port the proxy listens on for agent callbacks (default: 11601).',
  tun_name: 'Name for the TUN interface created on this machine.',
  laddr: '0.0.0.0 accepts agents from any interface.',
};

interface SpecState {
  local_bind: string;
  local_port: string;
  remote_bind: string;
  remote_port: string;
  target_host: string;
  target_port: string;
  agent_addr: string;
  listen_port: string;
  tun_name: string;
  laddr: string;
}

const EMPTY_SPEC: SpecState = {
  local_bind: '127.0.0.1',
  local_port: '',
  remote_bind: '127.0.0.1',
  remote_port: '',
  target_host: '',
  target_port: '',
  agent_addr: '',
  listen_port: '11601',
  tun_name: 'ligolo',
  laddr: '0.0.0.0',
};

export interface TunnelPrefill {
  label?: string;
  kind?: TunnelKind;
  targetHost?: string;
  targetPort?: number;
}

interface TunnelFormModalProps {
  open: boolean;
  onClose: () => void;
  engagementId: number;
  engagementName: string;
  onCreated: () => void;
  prefill?: TunnelPrefill | null;
}

export function TunnelFormModal({
  open,
  onClose,
  engagementId,
  engagementName,
  onCreated,
  prefill,
}: TunnelFormModalProps) {
  const { items: agents } = useAgents(engagementId);
  const [label, setLabel] = useState('');
  const [kind, setKind] = useState<TunnelKind>('ssh_dynamic');
  const [agentId, setAgentId] = useState<string>('');

  // The SSH server that carries the tunnel.
  const [sshUser, setSshUser] = useState('');
  const [sshHost, setSshHost] = useState('');
  const [sshPort, setSshPort] = useState('22');
  const [identityFile, setIdentityFile] = useState('');
  const [acceptNewHostKey, setAcceptNewHostKey] = useState(false);

  const [spec, setSpec] = useState<SpecState>(EMPTY_SPEC);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLabel(prefill?.label ?? '');
    setKind(prefill?.kind ?? 'ssh_dynamic');
    setAgentId('');
    setSshUser('');
    setSshHost('');
    setSshPort('22');
    setIdentityFile('');
    setAcceptNewHostKey(false);
    setSpec({
      ...EMPTY_SPEC,
      target_host: prefill?.targetHost ?? '',
      target_port: prefill?.targetPort ? String(prefill.targetPort) : '',
    });
    setError(null);
  }, [open, prefill]);

  const visibleFields = SPEC_FIELDS[kind] ?? [];
  const selectedKind = KIND_OPTIONS.find((option) => option.value === kind);

  const isLigolo = kind === 'ligolo';

  async function handleSubmit() {
    setError(null);

    const specPayload: Record<string, unknown> = {};

    if (isLigolo) {
      if (!spec.agent_addr.trim()) {
        setError('Agent address is required — the IP the ligolo agent connects from.');
        return;
      }
    } else {
      if (!sshUser.trim() || !sshHost.trim()) {
        setError('SSH user and host are required — they are how the tunnel is carried.');
        return;
      }
      specPayload.endpoint = {
        user: sshUser.trim(),
        host: sshHost.trim(),
        port: Number(sshPort) || 22,
        ...(identityFile.trim() ? { identity_file: identityFile.trim() } : {}),
        ...(acceptNewHostKey ? { strict_host_key_checking: false } : {}),
      };
    }

    for (const field of visibleFields) {
      const raw = spec[field];
      if (!raw) continue;
      specPayload[field] = field.endsWith('port') ? Number(raw) : raw;
    }

    if (isLigolo) {
      specPayload.selfcert = true;
    }

    setSubmitting(true);
    try {
      await createTunnel({
        engagement: engagementId,
        kind,
        label: label.trim(),
        spec: specPayload,
        agent: agentId ? Number(agentId) : undefined,
      });
      onCreated();
      onClose();
    } catch (err) {
      // Scope refusals arrive here. The message names the rejected target and
      // what the engagement does allow, so it is shown verbatim.
      setError(err instanceof ApiError ? err.detail : 'Failed to create tunnel.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={`New tunnel — ${engagementName}`}>
      <div className="space-y-4">
        <Field label="Label">
          <TextInput
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="sql via dmz-jump"
            autoFocus
          />
        </Field>

        <Field label="Kind" hint={selectedKind?.hint}>
          <Select value={kind} onChange={(e) => setKind(e.target.value as TunnelKind)}>
            {KIND_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </Select>
        </Field>

        {!isLigolo && <fieldset className="rounded-md border border-subtle p-3">
          <legend className="px-1 text-xs font-medium text-text-muted">SSH endpoint</legend>
          <div className="grid grid-cols-2 gap-3">
            <Field label="User">
              <TextInput value={sshUser} onChange={(e) => setSshUser(e.target.value)} placeholder="opsec" mono />
            </Field>
            <Field label="Host">
              <TextInput value={sshHost} onChange={(e) => setSshHost(e.target.value)} placeholder="10.4.0.10" mono />
            </Field>
            <Field label="Port">
              <TextInput value={sshPort} onChange={(e) => setSshPort(e.target.value)} placeholder="22" mono type="number" min={1} max={65535} />
            </Field>
            <Field label="Identity file" hint="Absolute path on the engine host.">
              <TextInput
                value={identityFile}
                onChange={(e) => setIdentityFile(e.target.value)}
                placeholder="/keys/acme.pem"
                mono
              />
            </Field>
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm text-text-secondary">
            <input
              type="checkbox"
              checked={acceptNewHostKey}
              onChange={(event) => setAcceptNewHostKey(event.target.checked)}
              className="accent-accent"
            />
            Accept an unknown host key on first connect
          </label>
        </fieldset>}

        {visibleFields.length > 0 && (
          <fieldset className="rounded-md border border-subtle p-3">
            <legend className="px-1 text-xs font-medium text-text-muted">{isLigolo ? 'ligolo-ng proxy' : 'Forwarding'}</legend>
            <div className="grid grid-cols-2 gap-3">
              {visibleFields.map((field) => {
                const isPort = field.endsWith('_port');
                return (
                  <Field key={field} label={FIELD_LABELS[field]} hint={FIELD_HINTS[field]}>
                    <TextInput
                      value={spec[field]}
                      onChange={(e) =>
                        setSpec((prev) => ({ ...prev, [field]: e.target.value }))
                      }
                      mono
                      {...(isPort ? { type: 'number', min: 1, max: 65535 } : {})}
                    />
                  </Field>
                );
              })}
            </div>
          </fieldset>
        )}

        {agents.length > 0 && (
          <Field label="Foothold" hint="Optional. Associates this tunnel with a known agent.">
            <Select value={agentId} onChange={(e) => setAgentId(e.target.value)}>
              <option value="">None</option>
              {agents.map((agent) => (
                <option key={agent.id} value={String(agent.id)}>
                  {agent.name}
                </option>
              ))}
            </Select>
          </Field>
        )}

        {error && (
          <p
            role="alert"
            className="rounded-md border border-subtle px-3 py-2 text-sm text-error"
          >
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Creating…' : 'Create tunnel'}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
