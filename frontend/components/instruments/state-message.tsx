import type { ReactNode } from "react";

export function StateMessage({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="grid gap-2 rounded-lg border border-dashed px-6 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children ? <div className="text-sm text-muted-foreground">{children}</div> : null}
    </div>
  );
}

export const NO_ACCESS = "You don't have access to this page.";
