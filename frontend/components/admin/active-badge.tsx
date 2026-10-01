import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

// Spec 17: Active/Inactive badge for the Users/GATC/LMO directories, modeled directly on
// components/applications/status-badge.tsx's variant/className split.
export function ActiveBadge({ active }: { active: boolean }) {
  if (active) {
    return (
      <Badge
        variant="outline"
        className={cn("border-transparent bg-success/10 text-success dark:bg-success/20")}
      >
        Active
      </Badge>
    );
  }
  return <Badge variant="outline">Inactive</Badge>;
}
