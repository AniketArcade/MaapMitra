"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type FormEvent } from "react";

import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { SelectField } from "@/components/select-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getApplicationMeta } from "@/lib/meta";
import type { Application, ApplicationMeta, Instrument, Page } from "@/lib/types";

function NewApplicationForm() {
  const router = useRouter();
  const preselected = useSearchParams().get("instrument_id") ?? "";
  const [meta, setMeta] = useState<ApplicationMeta | null>(null);
  const [instruments, setInstruments] = useState<Instrument[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [instrumentId, setInstrumentId] = useState(preselected);
  const [type, setType] = useState("VERIFICATION");
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    Promise.all([getApplicationMeta(), api<Page<Instrument>>("/instruments?page_size=100")]).then(
      ([m, page]) => {
        setMeta(m);
        setInstruments(page.items.filter((i) => i.active_application === null));
      },
      () => setLoadError(true),
    );
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
    if (!instrumentId) {
      setFieldErrors({ instrument_id: "Choose an instrument." });
      return;
    }
    setSubmitting(true);
    try {
      const created = await api<Application>("/applications", {
        method: "POST",
        body: JSON.stringify({
          instrument_id: instrumentId,
          application_type: type,
          ...(notes.trim() ? { business_notes: notes.trim() } : {}),
        }),
      });
      router.push(`/applications/${created.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        const { body: formLevel, ...fields } = err.fieldErrors;
        setError(formLevel ?? err.message);
        setFieldErrors(fields);
      } else {
        setError("Could not reach the server.");
      }
      setSubmitting(false);
    }
  }

  if (loadError) return <StateMessage title="Could not load the form. Please reload the page." />;
  if (!meta || !instruments) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (instruments.length === 0) {
    return (
      <StateMessage title="No instrument is available to apply for">
        Every instrument already has an application in progress, or none is registered yet.{" "}
        <Link href="/instruments/new" className="underline">
          Register an instrument
        </Link>
      </StateMessage>
    );
  }

  const instrumentOptions = instruments.map((i) => ({
    value: i.id,
    label: `${i.instrument_uid} · S/N ${i.serial_number} · ${i.capacity} ${i.capacity_unit}`,
  }));
  const typeOptions = meta.application_types.map((t) => ({ value: t.value, label: t.label }));

  return (
    <form onSubmit={onSubmit} className="grid max-w-xl gap-5" noValidate>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <SelectField
        name="instrument_id"
        label="Instrument"
        value={instrumentId}
        options={instrumentOptions}
        onChange={setInstrumentId}
        error={fieldErrors.instrument_id}
      />
      <SelectField
        name="application_type"
        label="Application type"
        value={type}
        options={typeOptions}
        onChange={setType}
        error={fieldErrors.application_type}
      />
      <div className="grid gap-1.5">
        <Label htmlFor="business_notes">Notes for the officer (optional)</Label>
        <Textarea
          id="business_notes"
          value={notes}
          maxLength={1000}
          onChange={(e) => setNotes(e.target.value)}
          aria-invalid={fieldErrors.business_notes ? true : undefined}
        />
        {fieldErrors.business_notes ? (
          <p className="text-sm text-destructive">{fieldErrors.business_notes}</p>
        ) : null}
      </div>
      <p className="text-sm text-muted-foreground">
        This creates a draft. You&apos;ll upload the required documents next, then submit.
      </p>
      <div>
        <Button type="submit" className="h-10" disabled={submitting}>
          {submitting ? "Creating…" : "Create draft"}
        </Button>
      </div>
    </form>
  );
}

export default function NewApplicationPage() {
  const { user } = useAuth();
  if (user?.role !== "BUSINESS") return <StateMessage title={NO_ACCESS} />;
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">Apply for verification</h1>
      <Suspense>
        <NewApplicationForm />
      </Suspense>
    </div>
  );
}
