"use client";

import { useRouter } from "next/navigation";

import { InstrumentForm } from "@/components/instruments/instrument-form";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { useAuth } from "@/lib/auth";

export default function NewInstrumentPage() {
  const { user } = useAuth();
  const router = useRouter();
  if (user?.role !== "BUSINESS") return <StateMessage title={NO_ACCESS} />;
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">Register an instrument</h1>
      <InstrumentForm mode="create" onSaved={(i) => router.push(`/instruments/${i.id}`)} />
    </div>
  );
}
