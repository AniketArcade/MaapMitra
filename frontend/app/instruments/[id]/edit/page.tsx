"use client";

import { useParams, useRouter } from "next/navigation";

import { InstrumentForm } from "@/components/instruments/instrument-form";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { useInstrument } from "@/components/instruments/use-instrument";
import { useAuth } from "@/lib/auth";

export default function EditInstrumentPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const state = useInstrument(id);

  if (user?.role !== "BUSINESS") return <StateMessage title={NO_ACCESS} />;
  if (state.kind === "loading") return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (state.kind === "not-found") return <StateMessage title="Instrument not found" />;
  if (state.kind !== "ready") return <StateMessage title="Could not load this instrument." />;

  return (
    <div className="grid gap-6">
      <div className="grid gap-1">
        <span className="font-mono text-sm text-muted-foreground">{state.instrument.instrument_uid}</span>
        <h1 className="text-2xl font-semibold">Edit instrument</h1>
      </div>
      <InstrumentForm
        mode="edit"
        initial={state.instrument}
        onSaved={(i) => router.push(`/instruments/${i.id}`)}
      />
    </div>
  );
}
