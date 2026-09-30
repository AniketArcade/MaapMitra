"use client";

import type { ReactNode } from "react";

import { Paperclip, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "cn";
import type { CategoryFieldSchema } from "@/lib/types";

// Ported from the donor prototype (MaapMitrafrontend/src/components/instruments/
// dynamic-field-renderer.tsx), adapted from its camelCase CategoryField shape to this
// backend's snake_case CategoryFieldSchema (GET /instruments/meta's `categories[].field_schema`,
// spec 16) and rebuilt on this repo's own ui/* primitives (@base-ui/react, not the donor's
// radix-based components) — see components/instruments/instrument-form.tsx for how it's wired
// into create/edit.
//
// Value shapes per field type (all loosely-typed — the 33 category schemas are data-driven, not
// one Zod/TS type per category):
//   text | select | toggle | date | file -> string
//   number                               -> number | ""
//   multiselect                          -> string[]
//   unit-number                          -> { value: number | ""; unit?: string }
//   range-band                           -> { qmin, qt, qmax: number | "" }
//   repeater                             -> Record<string, unknown>[]

type UnitNumberValue = { value?: number | string; unit?: string };
type RangeBandValue = { qmin?: number | string; qt?: number | string; qmax?: number | string };

/** Default value for a freshly-added field/row, keyed by field type. */
export function defaultValueForField(field: CategoryFieldSchema): unknown {
  switch (field.type) {
    case "unit-number":
      return { value: "", unit: field.unit ?? field.unit_options?.[0] ?? "" };
    case "range-band":
      return { qmin: "", qt: "", qmax: "" };
    case "multiselect":
    case "repeater":
      return [];
    default:
      return "";
  }
}

/** Initial category_values object for a category's full field list — used when the form's
 * category selection changes (a freshly-selected category has no prior values to preserve). */
export function initCategoryValues(fields: CategoryFieldSchema[]): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const field of fields) values[field.key] = defaultValueForField(field);
  return values;
}

function emptyRow(fields: CategoryFieldSchema[]): Record<string, unknown> {
  const row: Record<string, unknown> = {};
  for (const field of fields) row[field.key] = defaultValueForField(field);
  return row;
}

function isEmptyForField(field: CategoryFieldSchema, value: unknown): boolean {
  if (value === undefined || value === null) return true;
  switch (field.type) {
    case "multiselect":
    case "repeater":
      return !Array.isArray(value) || value.length === 0;
    case "number":
      return value === "" || Number.isNaN(Number(value));
    case "unit-number": {
      const v = value as UnitNumberValue;
      return v.value === undefined || v.value === "" || Number.isNaN(Number(v.value));
    }
    case "range-band": {
      const v = value as RangeBandValue;
      return [v.qmin, v.qt, v.qmax].some((x) => x === undefined || x === "");
    }
    default:
      return value === "";
  }
}

/** Top-level required-field-presence check only — mirrors the backend's own validation scope
 * exactly (spec 16 §7, backend/app/services/instruments.py's `_validate_category`: every
 * `field_schema` entry with `required: true` must have a non-null `category_values` entry;
 * repeater-row contents, range-band Qmin<Qt<Qmax ordering and unit-option membership are
 * deliberately out of scope there, so they stay out of scope here too). Treating an empty
 * string/array as "missing" (rather than only `null`/`undefined`, which is all the backend
 * checks) is a client-side nicety that never recurses into repeater rows or validates
 * range-band ordering — the backend remains the source of truth and will 422 anything this
 * misses via `category_values` (surfaced through ApiError.fieldErrors as usual). */
export function validateCategoryValues(
  fields: CategoryFieldSchema[],
  values: Record<string, unknown> | undefined | null,
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const field of fields) {
    // Category 11's "Max speed" only applies when Operating mode = Dynamic (its own help_text
    // says as much) — skip the required-check for a hidden field rather than blocking submit.
    if (field.key === "maxSpeed" && values?.operatingMode !== "Dynamic") continue;
    if (!field.required) continue;
    const value = values ? values[field.key] : undefined;
    if (isEmptyForField(field, value)) errors[field.key] = `${field.label} is required`;
  }
  return errors;
}

function FieldShell({
  htmlFor,
  label,
  required,
  error,
  helpText,
  legend,
  children,
}: {
  htmlFor: string;
  label: string;
  required?: boolean;
  error?: string;
  helpText?: string | null;
  legend?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-1.5">
      {legend ? (
        <span id={`${htmlFor}-legend`} className="text-sm font-medium">
          {label}
          {required ? " *" : ""}
        </span>
      ) : (
        <Label htmlFor={htmlFor}>
          {label}
          {required ? " *" : ""}
        </Label>
      )}
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} className="text-sm text-destructive">
          {error}
        </p>
      ) : helpText ? (
        <p id={`${htmlFor}-hint`} className="text-xs text-muted-foreground">
          {helpText}
        </p>
      ) : null}
    </div>
  );
}

export interface DynamicFieldRendererProps {
  fields: CategoryFieldSchema[];
  values: Record<string, unknown>;
  onChange: (key: string, value: unknown) => void;
  errors?: Record<string, string>;
  /** Disables every control — used when Instrument.locked_fields includes category_id/
   * category_values (an application is in progress). Never re-derive the lock rule client-side. */
  disabled?: boolean;
  className?: string;
}

/** The one renderer for all 33 instrument categories' field schemas. Switches on
 * CategoryFieldSchema.type and handles every shape the backend seeds:
 * text/number/select/multiselect/unit-number/range-band/repeater/toggle/date/file. */
export function DynamicFieldRenderer({
  fields,
  values,
  onChange,
  errors,
  disabled,
  className,
}: DynamicFieldRendererProps) {
  // Category 11's Max speed field only makes sense once Operating mode is Dynamic.
  const visibleFields = fields.filter(
    (field) => !(field.key === "maxSpeed" && values.operatingMode !== "Dynamic"),
  );

  return (
    <div className={cn("grid gap-5", className)}>
      {visibleFields.map((field) => (
        <FieldControl
          key={field.key}
          field={field}
          value={values[field.key]}
          onChange={(next) => onChange(field.key, next)}
          error={errors?.[field.key]}
          path={`category-${field.key}`}
          disabled={disabled}
        />
      ))}
    </div>
  );
}

interface FieldControlProps {
  field: CategoryFieldSchema;
  value: unknown;
  onChange: (value: unknown) => void;
  error?: string;
  path: string;
  disabled?: boolean;
}

function FieldControl({ field, value, onChange, error, path, disabled }: FieldControlProps) {
  switch (field.type) {
    case "text":
      return (
        <FieldShell htmlFor={path} label={field.label} required={field.required} error={error} helpText={field.help_text}>
          <Input
            id={path}
            value={(value as string) ?? ""}
            onChange={(e) => onChange(e.target.value)}
            aria-invalid={!!error}
            disabled={disabled}
          />
        </FieldShell>
      );

    case "number":
      return (
        <FieldShell htmlFor={path} label={field.label} required={field.required} error={error} helpText={field.help_text}>
          <Input
            id={path}
            type="number"
            value={value === undefined || value === null ? "" : (value as number | string)}
            min={field.min ?? undefined}
            max={field.max ?? undefined}
            onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
            aria-invalid={!!error}
            disabled={disabled}
          />
        </FieldShell>
      );

    case "select": {
      const options = field.options ?? field.presets ?? [];
      return (
        <FieldShell htmlFor={path} label={field.label} required={field.required} error={error} helpText={field.help_text}>
          <Select
            items={options}
            value={(value as string) || null}
            onValueChange={(v) => onChange(typeof v === "string" ? v : "")}
            disabled={disabled}
          >
            <SelectTrigger id={path} className="h-9 w-full" aria-invalid={!!error}>
              <SelectValue placeholder="Select…" />
            </SelectTrigger>
            <SelectContent>
              {options.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FieldShell>
      );
    }

    case "toggle": {
      const options = field.options ?? [];
      return (
        <FieldShell htmlFor={path} label={field.label} required={field.required} error={error} helpText={field.help_text} legend>
          <div
            role="radiogroup"
            aria-labelledby={`${path}-legend`}
            className="inline-flex w-fit rounded-lg border border-border p-1"
          >
            {options.map((option) => {
              const selected = value === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  disabled={disabled}
                  onClick={() => onChange(option.value)}
                  className={cn(
                    "min-h-9 min-w-24 rounded-md px-3 text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50",
                    "focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                    selected ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
        </FieldShell>
      );
    }

    case "multiselect": {
      const options = field.options ?? [];
      const selectedValues = Array.isArray(value) ? (value as string[]) : [];
      return (
        <FieldShell htmlFor={path} label={field.label} required={field.required} error={error} helpText={field.help_text} legend>
          <div role="group" aria-labelledby={`${path}-legend`} className="flex flex-col gap-2">
            {options.map((option) => {
              const checked = selectedValues.includes(option.value);
              return (
                <label
                  key={option.value}
                  htmlFor={`${path}-${option.value}`}
                  className="flex min-h-9 items-center gap-2 text-sm"
                >
                  <Checkbox
                    id={`${path}-${option.value}`}
                    checked={checked}
                    disabled={disabled}
                    onCheckedChange={(next) =>
                      onChange(
                        next
                          ? [...selectedValues, option.value]
                          : selectedValues.filter((v) => v !== option.value),
                      )
                    }
                  />
                  {option.label}
                </label>
              );
            })}
          </div>
        </FieldShell>
      );
    }

    case "unit-number": {
      const v = (value as UnitNumberValue | undefined) ?? {};
      return (
        <FieldShell htmlFor={path} label={field.label} required={field.required} error={error} helpText={field.help_text}>
          <div className="flex gap-2">
            <Input
              id={path}
              type="number"
              className="flex-1"
              value={v.value === undefined || v.value === null ? "" : v.value}
              onChange={(e) => onChange({ ...v, value: e.target.value === "" ? "" : Number(e.target.value) })}
              aria-invalid={!!error}
              disabled={disabled}
            />
            {field.unit ? (
              <span className="flex h-9 items-center rounded-lg border border-input bg-muted/40 px-2.5 text-sm text-muted-foreground">
                {field.unit}
              </span>
            ) : field.unit_options && field.unit_options.length > 0 ? (
              <Select
                items={field.unit_options.map((u) => ({ value: u, label: u }))}
                value={v.unit || field.unit_options[0]}
                onValueChange={(unit) => onChange({ ...v, unit: typeof unit === "string" ? unit : "" })}
                disabled={disabled}
              >
                <SelectTrigger className="w-24" aria-label={`${field.label} unit`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {field.unit_options.map((unit) => (
                    <SelectItem key={unit} value={unit}>
                      {unit}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : null}
          </div>
        </FieldShell>
      );
    }

    case "range-band": {
      const v = (value as RangeBandValue | undefined) ?? {};
      const helpText = `${field.unit ? `Unit: ${field.unit}. ` : ""}${field.help_text ?? "Qmin < Qt < Qmax"}`;
      return (
        <FieldShell htmlFor={path} label={field.label} required={field.required} error={error} helpText={helpText} legend>
          <div role="group" aria-labelledby={`${path}-legend`} className="grid grid-cols-3 gap-2">
            {(["qmin", "qt", "qmax"] as const).map((key) => (
              <div key={key} className="flex flex-col gap-1">
                <label htmlFor={`${path}-${key}`} className="text-xs font-medium text-muted-foreground uppercase">
                  {key}
                </label>
                <Input
                  id={`${path}-${key}`}
                  type="number"
                  value={v[key] === undefined || v[key] === null ? "" : v[key]}
                  onChange={(e) =>
                    onChange({ ...v, [key]: e.target.value === "" ? "" : Number(e.target.value) })
                  }
                  aria-invalid={!!error}
                  disabled={disabled}
                />
              </div>
            ))}
          </div>
        </FieldShell>
      );
    }

    case "date":
      return (
        <FieldShell htmlFor={path} label={field.label} required={field.required} error={error} helpText={field.help_text}>
          <Input
            id={path}
            type="date"
            value={typeof value === "string" ? value.slice(0, 10) : ""}
            onChange={(e) => onChange(e.target.value)}
            aria-invalid={!!error}
            disabled={disabled}
          />
        </FieldShell>
      );

    case "file":
      return (
        <FieldShell
          htmlFor={path}
          label={field.label}
          required={field.required}
          error={error}
          helpText={field.help_text ?? "Enter a file name or reference; this field does not upload a file."}
        >
          <div className="flex items-center gap-2">
            <Paperclip className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
            <Input
              id={path}
              placeholder="e.g. calibration-chart.pdf"
              value={(value as string) ?? ""}
              onChange={(e) => onChange(e.target.value)}
              aria-invalid={!!error}
              disabled={disabled}
            />
          </div>
        </FieldShell>
      );

    case "repeater": {
      const rows = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];
      const addLabel = field.repeater_label ?? "+ Add row";
      return (
        <FieldShell htmlFor={path} label={field.label} required={field.required} error={error} helpText={field.help_text} legend>
          <div role="group" aria-labelledby={`${path}-legend`} className="flex flex-col gap-3">
            {rows.map((row, index) => (
              <div key={index} className="flex flex-col gap-3 rounded-lg border border-border p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">Row {index + 1}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    disabled={disabled}
                    onClick={() => onChange(rows.filter((_, i) => i !== index))}
                    aria-label={`Remove row ${index + 1}`}
                  >
                    <Trash2 aria-hidden="true" />
                  </Button>
                </div>
                <div className="grid gap-4">
                  {(field.repeater_fields ?? []).map((subField) => (
                    <FieldControl
                      key={subField.key}
                      field={subField}
                      value={row[subField.key]}
                      onChange={(next) => {
                        const nextRows = [...rows];
                        nextRows[index] = { ...row, [subField.key]: next };
                        onChange(nextRows);
                      }}
                      path={`${path}-${index}-${subField.key}`}
                      disabled={disabled}
                    />
                  ))}
                </div>
              </div>
            ))}
            <Button
              type="button"
              variant="outline"
              disabled={disabled}
              onClick={() => onChange([...rows, emptyRow(field.repeater_fields ?? [])])}
              className="w-fit"
            >
              <Plus aria-hidden="true" />
              {addLabel}
            </Button>
          </div>
        </FieldShell>
      );
    }

    default:
      return null;
  }
}
