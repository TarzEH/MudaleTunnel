import { useState } from 'react';
import type { KeyboardEvent } from 'react';
import { isValidCidr } from '../utils/cidr';
import { IconX } from './icons';

interface CidrChipInputProps {
  value: string[];
  onChange: (next: string[]) => void;
}

/** Chip-style editor for a list of authorized CIDRs, with client-side validation. */
export function CidrChipInput({ value, onChange }: CidrChipInputProps) {
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<string | null>(null);

  function commitDraft() {
    const candidate = draft.trim();
    if (!candidate) return;
    if (!isValidCidr(candidate)) {
      setError(`"${candidate}" is not a valid CIDR (expected e.g. 10.0.0.0/8)`);
      return;
    }
    if (value.includes(candidate)) {
      setError(`${candidate} is already in scope`);
      return;
    }
    onChange([...value, candidate]);
    setDraft('');
    setError(null);
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      commitDraft();
    } else if (e.key === 'Backspace' && draft === '' && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  }

  function removeAt(idx: number) {
    onChange(value.filter((_, i) => i !== idx));
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-border-subtle bg-base px-2 py-1.5 focus-within:border-accent">
        {value.map((cidr, idx) => (
          <span
            key={cidr}
            className="inline-flex items-center gap-1 rounded-sm border border-border-subtle bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-text-primary"
          >
            {cidr}
            <button
              type="button"
              aria-label={`Remove ${cidr}`}
              onClick={() => removeAt(idx)}
              className="text-text-muted hover:text-error"
            >
              <IconX width={10} height={10} />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setError(null);
          }}
          onKeyDown={handleKeyDown}
          onBlur={commitDraft}
          placeholder={value.length === 0 ? '10.0.0.0/8, 172.16.0.0/12 …' : 'Add CIDR…'}
          className="min-w-[10ch] flex-1 bg-transparent font-mono text-xs text-text-primary placeholder:text-text-muted focus:outline-none"
        />
      </div>
      {error && <span className="text-xs text-error">{error}</span>}
      {value.length === 0 && !error && (
        <span className="text-xs text-warn">
          Empty scope means nothing is authorized — no tunnels, routes, or scans will be permitted.
        </span>
      )}
    </div>
  );
}
