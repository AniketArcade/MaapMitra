import { useFocusEffect } from "expo-router";
import { useCallback, useEffect, useRef, useState } from "react";

export type Async<T> = {
  status: "loading" | "error" | "ready";
  data: T | null;
  retry: () => void;
};

type Resolved<T> = { nonce: number; status: "ready" | "error"; data: T | null };

/**
 * Fetches on mount, on retry() and whenever the screen regains focus (e.g. coming back from a
 * form), keeping the previous data on screen while it reloads. Each caller has independent
 * loading/error state, so one failing section never blanks the rest of a screen.
 */
export function useAsync<T>(fetcher: () => Promise<T>): Async<T> {
  const [nonce, setNonce] = useState(0);
  const [resolved, setResolved] = useState<Resolved<T>>({ nonce: -1, status: "ready", data: null });
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

  const firstFocus = useRef(true);
  useFocusEffect(
    useCallback(() => {
      if (firstFocus.current) firstFocus.current = false;
      else setNonce((n) => n + 1);
    }, []),
  );

  const status = resolved.nonce === nonce ? resolved.status : resolved.data !== null ? "ready" : "loading";
  return { status, data: resolved.data, retry: () => setNonce((n) => n + 1) };
}
