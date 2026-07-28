/** Validates an IPv4 CIDR string, e.g. "10.0.0.0/8". */
export function isValidCidr(value: string): boolean {
  const trimmed = value.trim();
  const match = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\/(\d{1,2})$/.exec(trimmed);
  if (!match) return false;
  const octets = [match[1], match[2], match[3], match[4]];
  for (const octet of octets) {
    const n = Number(octet);
    if (Number.isNaN(n) || n < 0 || n > 255) return false;
  }
  const prefix = Number(match[5]);
  if (Number.isNaN(prefix) || prefix < 0 || prefix > 32) return false;
  return true;
}
