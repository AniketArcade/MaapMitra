import type { ReactNode } from "react";

import type { CategoryFieldSchema } from "@/lib/types";

// Ported from the donor prototype's category-values-summary.tsx: a read-only rendering of a
// category's field values, reusing the same field schema DynamicFieldRenderer edits. Used on
// the instrument detail page instead of reusing DynamicFieldRenderer itself in a "disabled"
// mode — a plain <dl> matches the rest of that page's Row-based layout (app/instruments/[id]/
// page.tsx) better than re-rendering interactive form controls read-only would.

type UnitNumberValue = { value?: number | string; unit?: string };
type RangeBandValue = { qmin?: number | string; qt?: number | string; qmax?: number | string };

function formatPlain(field: CategoryFieldSchema, value: unknown): string {
  if (value === undefined || value === null || value === "") return "—";
  switch (field.type) {
    case "unit-number": {
      const v = value as UnitNumberValue;
      if (v.value === undefined || v.value === "") return "—";
      return `${v.value}${v.unit ? ` ${v.unit}` : ""}`;
    }
    case "multiselect":
      return Array.isArray(value) && value.length ? (value as string[]).join(", ") : "—";
    default:
      return String(value);
  }
}

function formatValue(field: CategoryFieldSchema, value: unknown): ReactNode {
  if (value === undefined || value === null || value === "") return "—";

  switch (field.type) {
    case "range-band": {
      const v = value as RangeBandValue;
      if ([v.qmin, v.qt, v.qmax].some((x) => x === undefined || x === "")) return "—";
      return `Qmin ${v.qmin} · Qt ${v.qt} · Qmax ${v.qmax}${field.unit ? ` ${field.unit}` : ""}`;
    }
    case "repeater": {
      const rows = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
      if (!rows.length) return "—";
      return (
        <ul className="flex flex-col gap-1">
          {rows.map((row, index) => (
            <li key={index} className="text-xs text-foreground/90">
              {(field.repeater_fields ?? [])
                .map((subField) => `${subField.label}: ${formatPlain(subField, row[subField.key])}`)
                .join(" · ")}
            </li>
          ))}
        </ul>
      );
    }
    default:
      return formatPlain(field, value);
  }
}

export interface CategoryValuesSummaryProps {
  fields: CategoryFieldSchema[];
  values: Record<string, unknown>;
  className?: string;
}

/** Read-only rendering of a category's field values — for the instrument detail page. */
export function CategoryValuesSummary({ fields, values, className }: CategoryValuesSummaryProps) {
  return (
    <dl className={`grid grid-cols-1 gap-x-4 gap-y-3 text-sm sm:grid-cols-2 ${className ?? ""}`}>
      {fields.map((field) => (
        <div key={field.key} className={field.type === "repeater" ? "sm:col-span-2" : undefined}>
          <dt className="text-xs text-muted-foreground">{field.label}</dt>
          <dd>{formatValue(field, values[field.key])}</dd>
        </div>
      ))}
    </dl>
  );
}
