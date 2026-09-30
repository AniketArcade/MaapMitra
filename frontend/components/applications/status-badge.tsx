import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Colour by status group; the label always comes from /applications/meta.
// Success/warning states use the semantic tokens (no Badge variant for these yet), destructive
// and neutral states use Badge's own variants.
function classNameFor(status: string): string | undefined {
  if (status === "APPROVED" || status === "CERTIFICATE_ISSUED") {
    return "border-transparent bg-success/10 text-success dark:bg-success/20";
  }
  if (status === "DOCUMENTS_DEFICIENT") {
    return "border-transparent bg-warning/15 text-warning-foreground dark:bg-warning/20";
  }
  return undefined;
}

function variantFor(status: string): "secondary" | "default" | "outline" | "destructive" {
  if (status === "DRAFT") return "outline";
  if (status === "REJECTED") return "destructive";
  return "secondary";
}

export function StatusBadge({ status, label }: { status: string; label: string }) {
  const override = classNameFor(status);
  return (
    <Badge variant={override ? "outline" : variantFor(status)} className={cn(override)}>
      {label}
    </Badge>
  );
}
