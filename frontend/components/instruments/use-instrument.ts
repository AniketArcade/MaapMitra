"use client";

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { Instrument } from "@/lib/types";

export type InstrumentState =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "forbidden" }
  | { kind: "error" }
  | { kind: "ready"; instrument: Instrument };

export function useInstrument(id: string): InstrumentState {
  const [state, setState] = useState<InstrumentState>({ kind: "loading" });
  useEffect(() => {
    let cancelled = false;
    api<Instrument>(`/instruments/${id}`).then(
      (instrument) => !cancelled && setState({ kind: "ready", instrument }),
      (err: unknown) => {
        if (cancelled) return;
        // 404 covers both "missing" and "not yours / outside your jurisdiction"; 422 is a bad id.
        if (err instanceof ApiError && (err.status === 404 || err.status === 422)) {
          setState({ kind: "not-found" });
        } else if (err instanceof ApiError && err.status === 403) {
          setState({ kind: "forbidden" });
        } else {
          setState({ kind: "error" });
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [id]);
  return state;
}
