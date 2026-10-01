"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { FormField } from "@/components/auth/form-field";
import { SelectField } from "@/components/select-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { getPublicRegions } from "@/lib/meta";
import type { RegionMeta, RegisterRequest } from "@/lib/types";

function optional(value: FormDataEntryValue | null): string | undefined {
  const s = String(value ?? "").trim();
  return s || undefined;
}

function validate(body: RegisterRequest): Record<string, string> {
  const errors: Record<string, string> = {};
  if (body.organization_name.length < 2) errors.organization_name = "Enter the business name.";
  if (!body.state_code) errors.state_code = "Select a state.";
  if (!body.district_code) errors.district_code = "Select a district.";
  if (!body.full_name) errors.full_name = "Enter your name.";
  if (!body.email.includes("@")) errors.email = "Enter a valid email.";
  if (body.password.length < 8) errors.password = "At least 8 characters.";
  return errors;
}

export function RegisterForm() {
  const { register, status } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const [regions, setRegions] = useState<RegionMeta[] | null>(null);
  const [regionsError, setRegionsError] = useState(false);
  const [stateCode, setStateCode] = useState("");
  const [districtCode, setDistrictCode] = useState("");

  useEffect(() => {
    if (status === "authenticated") router.replace("/dashboard");
  }, [status, router]);

  useEffect(() => {
    getPublicRegions().then(setRegions, () => setRegionsError(true));
  }, []);

  const stateOptions = useMemo(
    () => (regions ?? []).map((r) => ({ value: r.state_code, label: r.state_name })),
    [regions],
  );
  const districtOptions = useMemo(
    () =>
      (regions?.find((r) => r.state_code === stateCode)?.districts ?? []).map((d) => ({
        value: d.code,
        label: d.name,
      })),
    [regions, stateCode],
  );

  function handleStateChange(value: string) {
    setStateCode(value);
    setDistrictCode("");
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body: RegisterRequest = {
      organization_name: String(form.get("organization_name") ?? "").trim(),
      registration_number: optional(form.get("registration_number")),
      address: optional(form.get("address")),
      state_code: stateCode,
      district_code: districtCode,
      full_name: String(form.get("full_name") ?? "").trim(),
      email: String(form.get("email") ?? "").trim(),
      phone: optional(form.get("phone")),
      password: String(form.get("password") ?? ""),
    };
    const clientErrors = validate(body);
    setFieldErrors(clientErrors);
    setError(null);
    if (Object.keys(clientErrors).length) return;

    setSubmitting(true);
    try {
      await register(body);
      router.replace("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        setFieldErrors(err.fieldErrors);
      } else {
        setError("Could not reach the server.");
      }
      setSubmitting(false);
    }
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle className="text-xl">Register your business</CardTitle>
        <CardDescription>Create an account to register instruments and apply for verification.</CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4" noValidate>
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          <fieldset className="grid gap-4">
            <legend className="mb-1 text-sm font-medium">Business</legend>
            <FormField name="organization_name" label="Business name" required error={fieldErrors.organization_name} />
            <FormField
              name="registration_number"
              label="Registration number (optional)"
              error={fieldErrors.registration_number}
            />
            <FormField name="address" label="Address (optional)" error={fieldErrors.address} />
            {regionsError ? (
              <Alert variant="destructive">
                <AlertDescription>Could not load states. Please reload the page.</AlertDescription>
              </Alert>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <SelectField
                  name="state_code"
                  label="State"
                  value={stateCode}
                  options={stateOptions}
                  onChange={handleStateChange}
                  placeholder={regions ? "Select…" : "Loading…"}
                  disabled={!regions}
                  error={fieldErrors.state_code}
                />
                <SelectField
                  name="district_code"
                  label="District"
                  value={districtCode}
                  options={districtOptions}
                  onChange={setDistrictCode}
                  placeholder={stateCode ? "Select…" : "Choose a state first"}
                  disabled={!stateCode}
                  error={fieldErrors.district_code}
                />
              </div>
            )}
          </fieldset>
          <fieldset className="grid gap-4">
            <legend className="mb-1 text-sm font-medium">Your account</legend>
            <FormField name="full_name" label="Full name" autoComplete="name" required error={fieldErrors.full_name} />
            <FormField name="email" label="Email" type="email" autoComplete="email" required error={fieldErrors.email} />
            <FormField name="phone" label="Phone (optional)" type="tel" autoComplete="tel" error={fieldErrors.phone} />
            <FormField
              name="password"
              label="Password"
              type="password"
              autoComplete="new-password"
              required
              hint="At least 8 characters."
              error={fieldErrors.password}
            />
          </fieldset>
          <Button type="submit" className="h-10" disabled={submitting}>
            {submitting ? "Creating account…" : "Create account"}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            Already registered?{" "}
            <Link href="/login" className="font-medium text-foreground underline">
              Log in
            </Link>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
