import type { VerifyResult } from "@api-types";

import { api } from "@/lib/api";

// No auth: the endpoint never 401s (30 requests/min/IP). Never links to the PDF.
export function getPublicVerify(certificateNumber: string): Promise<VerifyResult> {
  return api<VerifyResult>(`/public/verify/${encodeURIComponent(certificateNumber)}`);
}

/** "2028-10-01" -> "1 Oct 2028", without a timezone shift (the API sends plain dates). */
export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  if (!y || !m || !d) return iso;
  return `${d} ${months[m - 1]} ${y}`;
}
