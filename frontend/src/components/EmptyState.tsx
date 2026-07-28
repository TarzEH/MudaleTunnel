import type { ReactNode } from 'react';

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-border-subtle px-6 py-16 text-center">
      {icon && <div className="text-text-muted">{icon}</div>}
      <div className="text-sm font-medium text-text-primary">{title}</div>
      {description && <div className="max-w-sm text-sm text-text-secondary">{description}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
