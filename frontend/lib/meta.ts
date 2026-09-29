import { api } from "@/lib/api";
import type { InstrumentMeta } from "@/lib/types";

// Loaded once per page session; the backend is the single source of truth.
let metaPromise: Promise<InstrumentMeta> | null = null;

export function getInstrumentMeta(): Promise<InstrumentMeta> {
  metaPromise ??= api<InstrumentMeta>("/instruments/meta").catch((err: unknown) => {
    metaPromise = null; // allow a retry after a failure
    throw err;
  });
  return metaPromise;
}

export function typeLabel(meta: InstrumentMeta | null, value: string): string {
  return meta?.types.find((t) => t.value === value)?.label ?? value;
}

export function regionLabel(meta: InstrumentMeta | null, state: string, district: string): string {
  const region = meta?.regions.find((r) => r.state_code === state);
  const districtName = region?.districts.find((d) => d.code === district)?.name;
  return region && districtName ? `${districtName}, ${region.state_name}` : `${state} / ${district}`;
}
