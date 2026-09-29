"use client";

import { useEffect, useRef, useState } from "react";

export type AsyncStatus = "loading" | "error" | "ready";

export type Async<T> = {
  status: AsyncStatus;
  data: T | null;
  retry: () => void;
};

type Resolved<T> = { nonce: number; status: "ready" | "error"; data: T | null };

// Fetches on mount, on retry() and when the tab regains focus (no polling).
// Each caller gets independent loading/error/retry state, so one failing section
// never blanks the rest of a page.
//
// `status` is derived by comparing the current request generation (`nonce`) to the
// generation of the last resolved result, rather than an explicit "set loading" call in
// the effect body — the latter trips react-hooks/set-state-in-effect (a synchronous
// setState at the top of an effect forces an extra render pass).
export function useAsync<T>(fetcher: () => Promise<T>): Async<T> {
  const [nonce, setNonce] = useState(0);
  const [resolved, setResolved] = useState<Resolved<T>>({
    nonce: -1,
    status: "ready",
    data: null,
  });
  // Ref updated in an effect, not during render (react-hooks/refs), so an inline fetcher
  // closure doesn't need to sit in the fetch effect's own dependency array.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  useEffect(() => {
    let cancelled = false;
    fetcherRef.current().then(
      (data) => !cancelled && setResolved({ nonce, status: "ready", data }),
      () => !cancelled && setResolved((r) => ({ nonce, status: "error", data: r.data })),
    );
    return () => {
      cancelled = true;
    };
  }, [nonce]);

  useEffect(() => {
    function onVisible() {
      if (document.visibilityState === "visible") setNonce((n) => n + 1);
    }
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, []);

  const status: AsyncStatus = resolved.nonce === nonce ? resolved.status : "loading";
  return { status, data: resolved.data, retry: () => setNonce((n) => n + 1) };
}
