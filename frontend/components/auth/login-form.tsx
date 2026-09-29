"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { FormField } from "@/components/auth/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api";
import { safeNextPath, useAuth } from "@/lib/auth";

export function LoginForm() {
  const { login, status } = useAuth();
  const router = useRouter();
  const next = safeNextPath(useSearchParams().get("next"));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    setSubmitting(true);
    try {
      await login(String(form.get("email")), String(form.get("password")));
      router.replace(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server.");
      setSubmitting(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Log in</CardTitle>
        <CardDescription>Legal Metrology verification portal</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4" noValidate>
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <FormField name="email" label="Email" type="email" autoComplete="email" required />
          <FormField
            name="password"
            label="Password"
            type="password"
            autoComplete="current-password"
            required
          />
          <Button type="submit" className="h-10" disabled={submitting}>
            {submitting ? "Logging in…" : "Log in"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            New business?{" "}
            <Link href="/register" className="font-medium text-foreground underline">
              Register
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
