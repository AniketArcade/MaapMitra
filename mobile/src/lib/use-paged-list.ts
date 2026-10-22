import type { Page } from "@api-types";
import { useEffect, useState } from "react";

import { api, describeError } from "@/lib/api";

export const PAGE_SIZE = 20;

type List<T> = { items: T[]; total: number };

/**
 * Server-paged list with filters: `total` always comes from the API (never counted on the client).
 * Changing the filters or calling restart() starts again from page 1; loadMore() appends.
 */
export function usePagedList<T>(path: string, initialFilters: Record<string, string> = {}) {
  const [filters, setFilters] = useState(initialFilters);
  const [page, setPage] = useState(1);
  const [reload, setReload] = useState(0);
  const [list, setList] = useState<List<T> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const filterKey = JSON.stringify(filters);

  useEffect(() => {
    let cancelled = false;
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
    for (const [k, v] of Object.entries(JSON.parse(filterKey) as Record<string, string>)) {
      if (v) params.set(k, v);
    }
    api<Page<T>>(`${path}?${params}`).then(
      (data) => {
        if (cancelled) return;
        setList((prev) => ({
          total: data.total,
          items: page === 1 || !prev ? data.items : [...prev.items, ...data.items],
        }));
        setError(null);
        setLoading(false);
      },
      (err: unknown) => {
        if (cancelled) return;
        setError(describeError(err));
        setLoading(false);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [path, filterKey, page, reload]);

  return {
    list,
    filters,
    error,
    loading,
    /** Merges into the current filters and goes back to page 1. */
    setFilter: (patch: Record<string, string>) => {
      setFilters((f) => ({ ...f, ...patch }));
      setPage(1);
      setLoading(true);
    },
    loadMore: () => {
      setLoading(true);
      setPage((p) => p + 1);
    },
    restart: () => {
      setLoading(true);
      setPage(1);
      setReload((n) => n + 1);
    },
  };
}
