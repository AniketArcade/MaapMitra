import { api } from "@/lib/api";
import type { ApplicationMeta, InspectionMeta, InstrumentMeta } from "@/lib/types";

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

let applicationMetaPromise: Promise<ApplicationMeta> | null = null;

export function getApplicationMeta(): Promise<ApplicationMeta> {
  applicationMetaPromise ??= api<ApplicationMeta>("/applications/meta").catch((err: unknown) => {
    applicationMetaPromise = null;
    throw err;
  });
  return applicationMetaPromise;
}

export function labelFor(list: { value: string; label: string }[] | undefined, value: string): string {
  return list?.find((item) => item.value === value)?.label ?? value;
}

let inspectionMetaPromise: Promise<InspectionMeta> | null = null;

export function getInspectionMeta(): Promise<InspectionMeta> {
  inspectionMetaPromise ??= api<InspectionMeta>("/inspections/meta").catch((err: unknown) => {
    inspectionMetaPromise = null;
    throw err;
  });
  return inspectionMetaPromise;
}
