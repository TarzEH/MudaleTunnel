import { describe, it, expect } from 'vitest';
import { isValidCidr } from './cidr';

describe('isValidCidr', () => {
  it('accepts a standard private-network CIDR', () => {
    expect(isValidCidr('10.0.0.0/8')).toBe(true);
  });

  it('accepts a /32 single-host CIDR', () => {
    expect(isValidCidr('192.168.1.1/32')).toBe(true);
  });

  it('accepts /0 (default route)', () => {
    expect(isValidCidr('0.0.0.0/0')).toBe(true);
  });

  it('accepts a typical subnet', () => {
    expect(isValidCidr('172.16.0.0/12')).toBe(true);
  });

  it('trims whitespace', () => {
    expect(isValidCidr('  10.0.0.0/8  ')).toBe(true);
  });

  it('rejects octet > 255', () => {
    expect(isValidCidr('256.0.0.0/8')).toBe(false);
  });

  it('rejects prefix > 32', () => {
    expect(isValidCidr('10.0.0.0/33')).toBe(false);
  });

  it('rejects missing prefix', () => {
    expect(isValidCidr('10.0.0.0')).toBe(false);
  });

  it('rejects empty string', () => {
    expect(isValidCidr('')).toBe(false);
  });

  it('rejects garbage input', () => {
    expect(isValidCidr('not-a-cidr')).toBe(false);
  });

  it('rejects negative octet via string (e.g. -1.0.0.0/8)', () => {
    expect(isValidCidr('-1.0.0.0/8')).toBe(false);
  });

  it('rejects too few octets', () => {
    expect(isValidCidr('10.0.0/8')).toBe(false);
  });
});
