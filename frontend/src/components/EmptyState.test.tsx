import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EmptyState } from './EmptyState';

describe('EmptyState component', () => {
  it('renders the title', () => {
    render(<EmptyState title="No tunnels yet" />);
    expect(screen.getByText('No tunnels yet')).toBeInTheDocument();
  });

  it('renders the description when provided', () => {
    render(
      <EmptyState
        title="No tunnels"
        description="Create your first tunnel to get started."
      />
    );
    expect(screen.getByText('Create your first tunnel to get started.')).toBeInTheDocument();
  });

  it('does not render a description element when description is omitted', () => {
    const { container } = render(<EmptyState title="Empty" />);
    // Only the title div should be a direct text child — no description div
    const textDivs = container.querySelectorAll('.text-sm');
    expect(textDivs).toHaveLength(1);
  });

  it('renders an icon when provided', () => {
    render(
      <EmptyState
        title="No items"
        icon={<span data-testid="icon">ICON</span>}
      />
    );
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('renders an action slot when provided', () => {
    render(
      <EmptyState
        title="No items"
        action={<button>Create one</button>}
      />
    );
    expect(screen.getByRole('button', { name: 'Create one' })).toBeInTheDocument();
  });

  it('renders only the title when no optional props are given', () => {
    const { container } = render(<EmptyState title="Nothing here" />);
    // Should not render icon wrapper or action wrapper
    expect(container.querySelector('.text-text-muted')).toBeNull();
    expect(container.querySelector('.mt-2')).toBeNull();
  });
});
