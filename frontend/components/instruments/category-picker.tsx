"use client";

import { useMemo, useState } from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { InstrumentCategory } from "@/lib/types";

const NONE = "__none__";

type Props = {
  categories: InstrumentCategory[];
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
  error?: string;
};

/** Searchable picker over the 33 instrument categories (spec 16). The search box only filters
 * which options are listed — it never touches `value`, so typing a search term can't reset or
 * clear the current selection (CLAUDE.md: preserve values across interaction). The selected
 * category is always kept in the option list even if the current search text would otherwise
 * hide it, so the trigger can still resolve and show its label. */
export function CategoryPicker({ categories, value, onChange, disabled, error }: Props) {
  const [search, setSearch] = useState("");

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const base = q
      ? categories.filter((c) => c.name.toLowerCase().includes(q) || String(c.id).includes(q))
      : categories;
    if (value !== null && !base.some((c) => c.id === value)) {
      const selected = categories.find((c) => c.id === value);
      if (selected) return [selected, ...base];
    }
    return base;
  }, [categories, search, value]);

  const options = [
    { value: NONE, label: "No category (flat fields only)" },
    ...filtered.map((c) => ({ value: String(c.id), label: `${c.id}. ${c.name}` })),
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="grid gap-1.5">
        <Label htmlFor="category-search">Search categories</Label>
        <Input
          id="category-search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="e.g. weight, dispenser, meter…"
          disabled={disabled}
        />
        <p className="text-xs text-muted-foreground">
          {filtered.length} of {categories.length} categories shown{search ? ` for “${search}”` : ""}.
        </p>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="category_id">Instrument category (optional)</Label>
        <Select
          name="category_id"
          items={options}
          value={value === null ? NONE : String(value)}
          onValueChange={(v) => onChange(typeof v === "string" && v !== NONE ? Number(v) : null)}
          disabled={disabled}
        >
          <SelectTrigger id="category_id" className="h-10 w-full" aria-invalid={error ? true : undefined}>
            <SelectValue placeholder="Select a category…" />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
      </div>
    </div>
  );
}
