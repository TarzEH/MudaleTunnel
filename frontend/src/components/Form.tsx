import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';

export function Field({
  label,
  htmlFor,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor?: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-xs font-medium text-text-secondary">
        {label}
      </label>
      {children}
      {hint && !error && <span className="text-xs text-text-muted">{hint}</span>}
      {error && <span className="text-xs text-error">{error}</span>}
    </div>
  );
}

export function TextInput({ className = '', mono = false, ...rest }: InputHTMLAttributes<HTMLInputElement> & { mono?: boolean }) {
  return (
    <input
      className={`h-9 rounded-md border border-border-subtle bg-base px-3 text-sm text-text-primary placeholder:text-text-muted focus-visible:border-accent ${
        mono ? 'font-mono' : ''
      } ${className}`}
      {...rest}
    />
  );
}

export function TextArea({ className = '', ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={`min-h-20 rounded-md border border-border-subtle bg-base px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus-visible:border-accent ${className}`}
      {...rest}
    />
  );
}

export function Select({ className = '', children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={`h-9 rounded-md border border-border-subtle bg-base px-2.5 text-sm text-text-primary focus-visible:border-accent ${className}`}
      {...rest}
    >
      {children}
    </select>
  );
}
