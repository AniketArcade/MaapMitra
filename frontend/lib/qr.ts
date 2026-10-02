// A certificate QR encodes a full verify URL (see backend/app/pdf/certificate.py), so a camera
// decode usually yields a URL rather than a bare certificate number — extract it defensively.
export function parseCertificateNumberFromScan(raw: string): string {
  const trimmed = raw.trim();

  try {
    const url = new URL(trimmed);
    const segments = url.pathname.split("/").filter(Boolean);
    const last = segments.at(-1);
    if (last) return decodeURIComponent(last);
  } catch {
    // Not a URL — fall through to treating it as a bare certificate number.
  }

  return trimmed;
}
