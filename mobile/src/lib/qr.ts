// A certificate QR encodes `{PUBLIC_BASE_URL}/verify/{certificate_number}`, so a camera decode is
// usually a URL, but a bare number (typed by hand) must work too. Parsed with string ops, not
// `new URL()`: Hermes' URL implementation is incomplete.
const MAX_LENGTH = 64;

export function parseCertificateNumber(raw: string): string {
  const withoutQuery = raw.trim().split(/[?#]/)[0] ?? "";
  const segments = withoutQuery.split("/").filter(Boolean);
  const last = segments.at(-1) ?? "";
  let decoded = last;
  try {
    decoded = decodeURIComponent(last);
  } catch {
    // malformed escape: use the raw segment
  }
  return decoded.trim().slice(0, MAX_LENGTH);
}
