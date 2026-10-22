// Reference data is owned by the backend: never hard-code statuses, types, units or regions.
import type { ApplicationMeta, InspectionMeta, InstrumentMeta, RegionMeta } from "@api-types";

import { api } from "@/lib/api";

function cached<T>(path: string) {
  let promise: Promise<T> | null = null;
  return (): Promise<T> => {
    promise ??= api<T>(path).catch((err: unknown) => {
      promise = null; // allow a retry after a failure
      throw err;
    });
    return promise;
  };
}

export const getInstrumentMeta = cached<InstrumentMeta>("/instruments/meta");
export const getApplicationMeta = cached<ApplicationMeta>("/applications/meta");
export const getInspectionMeta = cached<InspectionMeta>("/inspections/meta");
export const getPublicRegions = cached<RegionMeta[]>("/public/regions"); // no auth: register form

export function labelFor(list: { value: string; label: string }[] | undefined, value: string): string {
  return list?.find((item) => item.value === value)?.label ?? value;
}

export function typeLabel(meta: InstrumentMeta | null | undefined, value: string): string {
  return meta?.types.find((t) => t.value === value)?.label ?? value;
}

export function regionLabel(meta: InstrumentMeta | null | undefined, state: string, district: string): string {
  const region = meta?.regions.find((r) => r.state_code === state);
  const districtName = region?.districts.find((d) => d.code === district)?.name;
  return region && districtName ? `${districtName}, ${region.state_name}` : `${state} / ${district}`;
}
