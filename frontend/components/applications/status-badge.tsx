import { Badge } from "@/components/ui/badge";

// Colour by status group; the label always comes from /applications/meta.
function variantFor(status: string): "secondary" | "default" | "outline" | "destructive" {
  if (status === "DRAFT") return "outline";
  if (status === "REJECTED") return "destructive";
  if (status === "APPROVED" || status === "CERTIFICATE_ISSUED") return "default";
  return "secondary";
}

export function StatusBadge({ status, label }: { status: string; label: string }) {
  return <Badge variant={variantFor(status)}>{label}</Badge>;
}
