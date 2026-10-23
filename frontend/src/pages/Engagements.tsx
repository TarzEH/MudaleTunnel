import { useState } from 'react';
import { useEngagementContext } from '../context/EngagementContext';
import { createEngagement, deleteEngagement, updateEngagement } from '../api/hooks';
import { ApiError } from '../api/client';
import type { Engagement, EngagementStatus } from '../api/types';
import { Badge } from '../components/Badge';
import { Button, IconButton } from '../components/Button';
import { CidrChipInput } from '../components/CidrChipInput';
import { EmptyState } from '../components/EmptyState';
import { Field, Select, TextArea, TextInput } from '../components/Form';
import { IconBriefcase, IconEdit, IconPlus, IconTrash } from '../components/icons';
import { Modal } from '../components/Modal';
import { SkeletonRows } from '../components/Skeleton';
import { engagementStatusTone, StatusDot } from '../components/StatusDot';

const STATUS_OPTIONS: EngagementStatus[] = ['planned', 'active', 'paused', 'closed'];

interface FormState {
  name: string;
  client: string;
  status: EngagementStatus;
  authorized_cidrs: string[];
  starts_on: string;
  ends_on: string;
  notes: string;
}

const EMPTY_FORM: FormState = {
  name: '',
  client: '',
  status: 'planned',
  authorized_cidrs: [],
  starts_on: '',
  ends_on: '',
  notes: '',
};

export function Engagements() {
  const { engagements, loading, reload, setSelectedId } = useEngagementContext();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Engagement | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setError(null);
    setModalOpen(true);
  }

  function openEdit(engagement: Engagement) {
    setEditing(engagement);
    setForm({
      name: engagement.name,
      client: engagement.client,
      status: engagement.status,
      authorized_cidrs: engagement.authorized_cidrs,
      starts_on: engagement.starts_on ?? '',
      ends_on: engagement.ends_on ?? '',
      notes: engagement.notes,
    });
    setError(null);
    setModalOpen(true);
  }

  async function handleSubmit() {
    if (!form.name.trim()) {
      setError('Name is required.');
      return;
    }
    setSubmitting(true);
    setError(null);
    const payload = {
      name: form.name.trim(),
      client: form.client.trim(),
      status: form.status,
      authorized_cidrs: form.authorized_cidrs,
      starts_on: form.starts_on || null,
      ends_on: form.ends_on || null,
      notes: form.notes,
    };
    try {
      if (editing) {
        await updateEngagement(editing.id, payload);
      } else {
        await createEngagement(payload);
      }
      setModalOpen(false);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : 'Failed to save engagement.');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(engagement: Engagement) {
    if (!window.confirm(`Delete engagement "${engagement.name}"? This cannot be undone.`)) return;
    try {
      await deleteEngagement(engagement.id);
      reload();
    } catch (err) {
      console.error('Failed to delete engagement', err);
      setError(err instanceof ApiError ? err.detail : 'Failed to delete engagement.');
    }
  }

  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border-subtle px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Engagements</h1>
          <p className="text-sm text-text-secondary">Scoped authorization windows for pivoting and scanning</p>
        </div>
        <Button variant="primary" onClick={openCreate}>
          <IconPlus /> New engagement
        </Button>
      </header>

      <div className="flex-1 overflow-auto px-6 py-4">
        {!loading && engagements.length === 0 ? (
          <EmptyState
            icon={<IconBriefcase width={28} height={28} />}
            title="No engagements yet"
            description="Create an engagement to define its authorized CIDR scope before deploying agents or tunnels."
            action={
              <Button variant="primary" onClick={openCreate}>
                <IconPlus /> New engagement
              </Button>
            }
          />
        ) : (
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border-subtle text-left text-xs text-text-muted">
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Name</th>
                <th className="px-4 py-2 font-medium">Client</th>
                <th className="px-4 py-2 font-medium">Scope</th>
                <th className="px-4 py-2 font-medium">Tunnels</th>
                <th className="px-4 py-2 font-medium">Scans</th>
                <th className="px-4 py-2 font-medium">Agents</th>
                <th className="px-4 py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <SkeletonRows rows={4} columns={8} />
              ) : (
                engagements.map((engagement) => (
                  <tr key={engagement.id} className="border-b border-border-subtle hover:bg-surface">
                    <td className="px-4 py-3">
                      <StatusDot tone={engagementStatusTone(engagement.status)} label={engagement.status} />
                    </td>
                    <td className="px-4 py-3">
                      <button
                        className="text-text-primary hover:underline"
                        onClick={() => {
                          setSelectedId(engagement.id);
                          openEdit(engagement);
                        }}
                      >
                        {engagement.name}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-text-secondary">{engagement.client || '—'}</td>
                    <td className="px-4 py-3">
                      {engagement.authorized_cidrs.length === 0 ? (
                        <Badge tone="warn">empty scope</Badge>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {engagement.authorized_cidrs.slice(0, 2).map((cidr) => (
                            <Badge key={cidr} mono>
                              {cidr}
                            </Badge>
                          ))}
                          {engagement.authorized_cidrs.length > 2 && (
                            <Badge>+{engagement.authorized_cidrs.length - 2}</Badge>
                          )}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3 font-mono text-text-secondary">{engagement.tunnel_count}</td>
                    <td className="px-4 py-3 font-mono text-text-secondary">{engagement.scan_count}</td>
                    <td className="px-4 py-3 font-mono text-text-secondary">{engagement.agent_count}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <IconButton aria-label={`Edit ${engagement.name}`} onClick={() => openEdit(engagement)}>
                          <IconEdit />
                        </IconButton>
                        <IconButton
                          aria-label={`Delete ${engagement.name}`}
                          onClick={() => handleDelete(engagement)}
                        >
                          <IconTrash />
                        </IconButton>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        )}
      </div>

      <EngagementModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        form={form}
        setForm={setForm}
        onSubmit={handleSubmit}
        submitting={submitting}
        error={error}
        isEditing={Boolean(editing)}
      />
    </div>
  );
}

function EngagementModal({
  open,
  onClose,
  form,
  setForm,
  onSubmit,
  submitting,
  error,
  isEditing,
}: {
  open: boolean;
  onClose: () => void;
  form: FormState;
  setForm: (updater: (prev: FormState) => FormState) => void;
  onSubmit: () => void;
  submitting: boolean;
  error: string | null;
  isEditing: boolean;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={isEditing ? 'Edit engagement' : 'New engagement'}
      widthClassName="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button variant="primary" onClick={onSubmit} disabled={submitting}>
            {submitting ? 'Saving…' : isEditing ? 'Save changes' : 'Create engagement'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name" htmlFor="eng-name">
            <TextInput
              id="eng-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </Field>
          <Field label="Client" htmlFor="eng-client">
            <TextInput
              id="eng-client"
              value={form.client}
              onChange={(e) => setForm((f) => ({ ...f, client: e.target.value }))}
            />
          </Field>
        </div>

        <div className="grid grid-cols-3 gap-3">
          <Field label="Status" htmlFor="eng-status">
            <Select
              id="eng-status"
              value={form.status}
              onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as EngagementStatus }))}
            >
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Starts on" htmlFor="eng-start">
            <input
              id="eng-start"
              type="date"
              value={form.starts_on ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, starts_on: e.target.value }))}
              className="h-9 rounded-md border border-border-subtle bg-base px-2.5 text-sm text-text-primary focus-visible:border-accent"
            />
          </Field>
          <Field label="Ends on" htmlFor="eng-end">
            <input
              id="eng-end"
              type="date"
              value={form.ends_on ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, ends_on: e.target.value }))}
              className="h-9 rounded-md border border-border-subtle bg-base px-2.5 text-sm text-text-primary focus-visible:border-accent"
            />
          </Field>
        </div>

        <Field label="Authorized CIDRs">
          <CidrChipInput
            value={form.authorized_cidrs}
            onChange={(next) => setForm((f) => ({ ...f, authorized_cidrs: next }))}
          />
        </Field>

        <Field label="Notes" htmlFor="eng-notes">
          <TextArea
            id="eng-notes"
            value={form.notes}
            onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
          />
        </Field>

        {error && (
          <div className="rounded-md border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
            {error}
          </div>
        )}
      </div>
    </Modal>
  );
}
