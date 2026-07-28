import { useEffect, useState } from 'react';
import { createTunnel, useAgents } from '../api/hooks';
import { ApiError } from '../api/client';
import type { TunnelKind } from '../api/types';
import { Button } from './Button';
import { Field, Select, TextArea, TextInput } from './Form';
import { Modal } from './Modal';

const KIND_OPTIONS: { value: TunnelKind; label: string }[] = [
  { value: 'ssh_local', label: 'SSH local forward' },
  { value: 'ssh_dynamic', label: 'SSH dynamic (SOCKS)' },
  { value: 'ssh_remote', label: 'SSH remote forward' },
  { value: 'ssh_remote_dynamic', label: 'SSH remote dynamic' },
  { value: 'ligolo_tun', label: 'Ligolo tun interface' },
];

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

interface SpecState {
  listen_host: string;
  listen_port: string;
  target_host: string;
  target_port: string;
  cidr: string;
}

const EMPTY_SPEC: SpecState = {
  listen_host: '127.0.0.1',
  listen_port: '',
  target_host: '',
  target_port: '',
  cidr: '',
};

function specFieldsForKind(kind: TunnelKind): Array<keyof SpecState> {
  switch (kind) {
    case 'ssh_local':
      return ['listen_host', 'listen_port', 'target_host', 'target_port'];
    case 'ssh_remote':
      return ['listen_port', 'target_host', 'target_port'];
    case 'ssh_dynamic':
      return ['listen_host', 'listen_port'];
    case 'ssh_remote_dynamic':
      return ['listen_port'];
    case 'ligolo_tun':
      return ['cidr'];
    default:
      return [];
  }
}

const FIELD_LABELS: Record<keyof SpecState, string> = {
  listen_host: 'Listen host',
  listen_port: 'Listen port',
  target_host: 'Target host',
  target_port: 'Target port',
  cidr: 'Routed CIDR',
};

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
  const [description, setDescription] = useState('');
  const [kind, setKind] = useState<TunnelKind>('ssh_local');
  const [agentId, setAgentId] = useState<string>('');
  const [spec, setSpec] = useState<SpecState>(EMPTY_SPEC);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setLabel(prefill?.label ?? '');
    setDescription('');
    setKind(prefill?.kind ?? 'ssh_local');
    setAgentId('');
    setSpec({
      ...EMPTY_SPEC,
      target_host: prefill?.targetHost ?? '',
      target_port: prefill?.targetPort ? String(prefill.targetPort) : '',
    });
    setError(null);
  }, [open, prefill]);

  const visibleFields = specFieldsForKind(kind);

  async function handleSubmit() {
    setError(null);
    if (!label.trim()) {
      setError('Label is required.');
      return;
    }
    const specPayload: Record<string, unknown> = {};
    for (const field of visibleFields) {
      const raw = spec[field];
      if (!raw) continue;
      specPayload[field] = field.endsWith('port') ? Number(raw) : raw;
    }
    setSubmitting(true);
    try {
      await createTunnel({
        engagement: engagementId,
        kind,
        label: label.trim(),
        description: description.trim() || undefined,
        spec: specPayload,
        agent: agentId ? Number(agentId) : undefined,
      });
      onCreated();
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError('Failed to create tunnel.');
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="New tunnel"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? 'Creating…' : 'Create tunnel'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field label="Engagement">
          <TextInput value={engagementName} disabled mono />
        </Field>
        <Field label="Label" htmlFor="tunnel-label">
          <TextInput
            id="tunnel-label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="jump-to-dmz"
            mono
          />
        </Field>
        <Field label="Description (optional)" htmlFor="tunnel-description">
          <TextArea
            id="tunnel-description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What this tunnel is for"
          />
        </Field>
        <Field label="Kind" htmlFor="tunnel-kind">
          <Select id="tunnel-kind" value={kind} onChange={(e) => setKind(e.target.value as TunnelKind)}>
            {KIND_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Agent (optional)" htmlFor="tunnel-agent">
          <Select id="tunnel-agent" value={agentId} onChange={(e) => setAgentId(e.target.value)}>
            <option value="">No agent</option>
            {agents.map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name} ({agent.status})
              </option>
            ))}
          </Select>
        </Field>

        {visibleFields.length > 0 && (
          <div className="rounded-md border border-border-subtle p-3">
            <div className="mb-3 text-xs font-medium text-text-muted">Spec</div>
            <div className="grid grid-cols-2 gap-3">
              {visibleFields.map((field) => (
                <Field key={field} label={FIELD_LABELS[field]} htmlFor={`spec-${field}`}>
                  <TextInput
                    id={`spec-${field}`}
                    value={spec[field]}
                    onChange={(e) => setSpec((s) => ({ ...s, [field]: e.target.value }))}
                    mono
                  />
                </Field>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
            {error}
          </div>
        )}
      </div>
    </Modal>
  );
}
