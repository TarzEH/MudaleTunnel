import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusDot, tunnelStatusTone, agentStatusTone, scanStatusTone } from './StatusDot';

describe('StatusDot component', () => {
  it('renders the label text', () => {
    render(<StatusDot tone="ok" label="Connected" />);
    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('renders with different tones without crashing', () => {
    const tones = ['ok', 'warn', 'error', 'info', 'neutral'] as const;
    for (const tone of tones) {
      const { unmount } = render(<StatusDot tone={tone} label={`Status: ${tone}`} />);
      expect(screen.getByText(`Status: ${tone}`)).toBeInTheDocument();
      unmount();
    }
  });

  it('applies the correct background color for the dot', () => {
    const { container } = render(<StatusDot tone="ok" label="Active" />);
    const dot = container.querySelector('[aria-hidden="true"]');
    expect(dot).toHaveStyle({ backgroundColor: 'var(--status-ok)' });
  });

  it('applies custom className', () => {
    const { container } = render(
      <StatusDot tone="neutral" label="Idle" className="mt-4" />
    );
    const wrapper = container.firstChild as HTMLElement;
    expect(wrapper.className).toContain('mt-4');
  });
});

describe('tunnelStatusTone', () => {
  it('maps "active" to ok', () => {
    expect(tunnelStatusTone('active')).toBe('ok');
  });

  it('maps "starting" to warn', () => {
    expect(tunnelStatusTone('starting')).toBe('warn');
  });

  it('maps "stopping" to warn', () => {
    expect(tunnelStatusTone('stopping')).toBe('warn');
  });

  it('maps "failed" to error', () => {
    expect(tunnelStatusTone('failed')).toBe('error');
  });

  it('maps "stopped" to neutral', () => {
    expect(tunnelStatusTone('stopped')).toBe('neutral');
  });

  it('maps unknown status to neutral', () => {
    expect(tunnelStatusTone('something_else')).toBe('neutral');
  });
});

describe('agentStatusTone', () => {
  it('maps "online" to ok', () => {
    expect(agentStatusTone('online')).toBe('ok');
  });

  it('maps "pending" to warn', () => {
    expect(agentStatusTone('pending')).toBe('warn');
  });

  it('maps "offline" to neutral', () => {
    expect(agentStatusTone('offline')).toBe('neutral');
  });

  it('maps "retired" to error', () => {
    expect(agentStatusTone('retired')).toBe('error');
  });
});

describe('scanStatusTone', () => {
  it('maps "completed" to ok', () => {
    expect(scanStatusTone('completed')).toBe('ok');
  });

  it('maps "running" to warn', () => {
    expect(scanStatusTone('running')).toBe('warn');
  });

  it('maps "failed" to error', () => {
    expect(scanStatusTone('failed')).toBe('error');
  });

  it('maps "timed_out" to error', () => {
    expect(scanStatusTone('timed_out')).toBe('error');
  });

  it('maps "cancelled" to neutral', () => {
    expect(scanStatusTone('cancelled')).toBe('neutral');
  });
});
