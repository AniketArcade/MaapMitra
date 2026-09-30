"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { CategoryValuesSummary } from "@/components/instruments/category-values-summary";
import { NO_ACCESS, StateMessage } from "@/components/instruments/state-message";
import { useInstrument } from "@/components/instruments/use-instrument";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { categoryById, getInstrumentMeta, regionLabel, typeLabel } from "@/lib/meta";
import type { InstrumentMeta } from "@/lib/types";

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-0.5 sm:grid-cols-[12rem_1fr]">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

export default function InstrumentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const state = useInstrument(id);
  const [meta, setMeta] = useState<InstrumentMeta | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    getInstrumentMeta().then(setMeta, () => undefined);
  }, []);

  if (state.kind === "loading") return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (state.kind === "not-found") return <StateMessage title="Instrument not found" />;
  if (state.kind === "forbidden") return <StateMessage title={NO_ACCESS} />;
  if (state.kind === "error") return <StateMessage title="Could not load this instrument." />;

  const i = state.instrument;
  const canEdit = user?.role === "BUSINESS";
  const category = categoryById(meta, i.category_id);

  async function onDelete() {
    setDeleting(true);
    setDeleteError(null);
    try {
      await api<void>(`/instruments/${i.id}`, { method: "DELETE" });
      router.push("/instruments");
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Could not reach the server.");
      setDeleting(false);
    }
  }

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="grid gap-1">
          <span className="font-mono text-sm text-muted-foreground">{i.instrument_uid}</span>
          <h1 className="text-2xl font-semibold">
            {typeLabel(meta, i.instrument_type)} · {i.capacity} {i.capacity_unit}
          </h1>
        </div>
        {canEdit ? (
          <div className="flex flex-wrap gap-2">
            {i.active_application ? (
              <Link href={`/applications/${i.active_application.id}`} className={buttonVariants()}>
                View application {i.active_application.application_number}
              </Link>
            ) : (
              <Link href={`/applications/new?instrument_id=${i.id}`} className={buttonVariants()}>
                Apply for verification
              </Link>
            )}
            <Link href={`/instruments/${i.id}/edit`} className={buttonVariants({ variant: "outline" })}>
              Edit
            </Link>
            <Button variant="destructive" onClick={() => setConfirmOpen(true)}>
              Delete
            </Button>
          </div>
        ) : null}
      </div>

      <dl className="grid gap-3 rounded-lg border p-4">
        <Row label="Owner" value={i.organization_name} />
        <Row label="Manufacturer" value={i.manufacturer} />
        <Row label="Model" value={i.model} />
        <Row label="Serial number" value={i.serial_number} />
        <Row label="Maximum capacity" value={`${i.capacity} ${i.capacity_unit}`} />
        <Row label="Accuracy class" value={i.accuracy_class ? `Class ${i.accuracy_class}` : "Not specified"} />
        <Row label="Address" value={i.address} />
        <Row label="Region" value={regionLabel(meta, i.state_code, i.district_code)} />
        <Row
          label="Coordinates"
          value={i.latitude !== null && i.longitude !== null ? `${i.latitude}, ${i.longitude}` : "Not provided"}
        />
        <Row label="Registered" value={new Date(i.created_at).toLocaleString()} />
      </dl>

      {category ? (
        <div className="grid gap-3 rounded-lg border p-4">
          <h2 className="text-sm font-medium">
            Category: {category.id}. {category.name}
          </h2>
          <CategoryValuesSummary fields={category.field_schema} values={i.category_values ?? {}} />
        </div>
      ) : i.category_id !== null ? (
        <Alert>
          <AlertDescription>
            This instrument has a category assigned (id {i.category_id}), but its schema could not
            be loaded.
          </AlertDescription>
        </Alert>
      ) : null}

      {!canEdit && i.active_application ? (
        <p className="text-sm">
          Application in progress:{" "}
          <Link href={`/applications/${i.active_application.id}`} className="underline">
            {i.active_application.application_number}
          </Link>
        </p>
      ) : null}
      {canEdit && i.active_application ? (
        <p className="text-sm text-muted-foreground">
          While an application is in progress, the serial number, capacity and location can&apos;t be
          changed.
        </p>
      ) : null}

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete this instrument?</DialogTitle>
            <DialogDescription>
              {i.instrument_uid} (S/N {i.serial_number}) will be permanently removed. This can’t be
              undone.
            </DialogDescription>
          </DialogHeader>
          {deleteError ? (
            <Alert variant="destructive">
              <AlertDescription>{deleteError}</AlertDescription>
            </Alert>
          ) : null}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)} disabled={deleting}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={() => void onDelete()} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
