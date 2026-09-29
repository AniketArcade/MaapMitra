"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { ADMIN_ROLES, type Instrument, type Page, type User } from "@/lib/types";

function InstrumentCount() {
  const [total, setTotal] = useState<number | null>(null);
  useEffect(() => {
    api<Page<Instrument>>("/instruments?page_size=1").then(
      (page) => setTotal(page.total),
      () => setTotal(null),
    );
  }, []);
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-sm">
        {total === null ? "Registered instruments" : `${total} registered instrument${total === 1 ? "" : "s"}`}
      </span>
      <div className="flex gap-2">
        <Link href="/instruments" className={buttonVariants({ variant: "outline", size: "sm" })}>
          View all
        </Link>
        <Link href="/instruments/new" className={buttonVariants({ size: "sm" })}>
          Register instrument
        </Link>
      </div>
    </div>
  );
}

function useTotal(path: string): number | null {
  const [total, setTotal] = useState<number | null>(null);
  useEffect(() => {
    api<Page<unknown>>(path).then(
      (page) => setTotal(page.total),
      () => setTotal(null),
    );
  }, [path]);
  return total;
}

function ApplicationCount() {
  const total = useTotal("/applications?page_size=1");
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-sm">
        {total === null ? "Applications" : `${total} application${total === 1 ? "" : "s"}`}
      </span>
      <Link href="/applications" className={buttonVariants({ variant: "outline", size: "sm" })}>
        View applications
      </Link>
    </div>
  );
}

function ReviewQueue() {
  const total = useTotal("/applications?status=SUBMITTED&page_size=1");
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-sm">
        {total === null ? "Submitted, awaiting review" : `${total} submitted, awaiting review`}
      </span>
      <Link href="/applications?status=SUBMITTED" className={buttonVariants({ size: "sm" })}>
        Review queue
      </Link>
    </div>
  );
}

function JurisdictionLink() {
  return (
    <div className="flex flex-wrap gap-2">
      <Link href="/instruments" className={buttonVariants({ variant: "outline", size: "sm" })}>
        View instruments
      </Link>
      <Link href="/applications" className={buttonVariants({ variant: "outline", size: "sm" })}>
        View applications
      </Link>
    </div>
  );
}

function RoleCard({ user }: { user: User }) {
  if (user.role === "BUSINESS") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{user.organization_name}</CardTitle>
          <CardDescription>Business dashboard</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <InstrumentCount />
          <ApplicationCount />
          <p className="text-sm text-muted-foreground">Certificates will appear here.</p>
        </CardContent>
      </Card>
    );
  }
  if (user.role === "LM_OFFICER") {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Officer dashboard</CardTitle>
          <CardDescription>
            Jurisdiction: {user.state_code} / {user.district_code}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <ReviewQueue />
          <p className="text-sm text-muted-foreground">Scheduled inspections will appear here.</p>
          <div>
            <JurisdictionLink />
          </div>
        </CardContent>
      </Card>
    );
  }
  if (ADMIN_ROLES.includes(user.role)) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Admin dashboard</CardTitle>
          <CardDescription>
            Scope: {user.state_code ?? "All states"}
            {user.district_code ? ` / ${user.district_code}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          <p className="text-sm text-muted-foreground">
            Statistics, users and audit logs will appear here.
          </p>
          <div>
            <JurisdictionLink />
          </div>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>GATC dashboard</CardTitle>
        <CardDescription>{user.organization_name}</CardDescription>
      </CardHeader>
      <CardContent className="text-sm text-muted-foreground">
        Assigned verifications will appear here.
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="grid gap-6">
      <h1 className="text-2xl font-semibold">
        Welcome, {user.full_name} <span className="text-base font-normal text-muted-foreground">({user.role})</span>
      </h1>
      <RoleCard user={user} />
    </div>
  );
}
