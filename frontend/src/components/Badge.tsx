import type { ReactNode } from 'react';

interface BadgeProps {
  children: ReactNode;
  tone?: 'neutral' | 'ok' | 'warn' | 'error' | 'info';
  mono?: boolean;
  className?: string;
}

const TONE_CLASSES: Record<NonNullable<BadgeProps['tone']>, string> = {
  neutral: 'border-border-subtle text-text-secondary',
  ok: 'border-ok/40 text-ok',
  warn: 'border-warn/40 text-warn',
  error: 'border-error/40 text-error',
  info: 'border-info/40 text-info',
};

export function Badge({ children, tone = 'neutral', mono = false, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-sm border px-1.5 py-0.5 text-xs leading-none ${
        TONE_CLASSES[tone]
      } ${mono ? 'font-mono' : ''} ${className}`}
    >
      {children}
    </span>
  );
}
