import { describe, it, expect } from 'vitest';
import { formatRelativeTime, formatDuration } from './time';

describe('formatRelativeTime', () => {
  const now = new Date('2026-10-23T12:00:00Z').getTime();

  it('returns "just now" for timestamps within 5 seconds', () => {
    expect(formatRelativeTime('2026-10-23T11:59:57Z', now)).toBe('just now');
  });

  it('returns seconds ago for recent past', () => {
    expect(formatRelativeTime('2026-10-23T11:59:30Z', now)).toBe('30s ago');
  });

  it('returns minutes ago', () => {
    expect(formatRelativeTime('2026-10-23T11:55:00Z', now)).toBe('5m ago');
  });

  it('returns hours ago', () => {
    expect(formatRelativeTime('2026-10-23T09:00:00Z', now)).toBe('3h ago');
  });

  it('returns days ago', () => {
    expect(formatRelativeTime('2026-10-20T12:00:00Z', now)).toBe('3d ago');
  });

  it('returns future time with "in" prefix', () => {
    expect(formatRelativeTime('2026-10-23T12:05:00Z', now)).toBe('in 5m');
  });

  it('returns dash for null', () => {
    expect(formatRelativeTime(null)).toBe('—');
  });

  it('returns dash for undefined', () => {
    expect(formatRelativeTime(undefined)).toBe('—');
  });

  it('returns dash for invalid ISO string', () => {
    expect(formatRelativeTime('not-a-date')).toBe('—');
  });
});

describe('formatDuration', () => {
  it('formats seconds only', () => {
    expect(formatDuration(45)).toBe('45s');
  });

  it('formats minutes and seconds', () => {
    expect(formatDuration(125)).toBe('2m 5s');
  });

  it('formats hours and minutes', () => {
    expect(formatDuration(5040)).toBe('1h 24m');
  });

  it('formats days and hours', () => {
    expect(formatDuration(90000)).toBe('1d 1h');
  });

  it('formats zero seconds', () => {
    expect(formatDuration(0)).toBe('0s');
  });

  it('returns dash for null', () => {
    expect(formatDuration(null)).toBe('—');
  });

  it('returns dash for undefined', () => {
    expect(formatDuration(undefined)).toBe('—');
  });

  it('returns dash for NaN', () => {
    expect(formatDuration(NaN)).toBe('—');
  });

  it('clamps negative values to 0s', () => {
    expect(formatDuration(-10)).toBe('0s');
  });
});
