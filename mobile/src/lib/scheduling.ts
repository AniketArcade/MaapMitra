// Date math for scheduling. "Today" is always computed in the backend's scheduling timezone
// (ApplicationMeta.scheduling.timezone), never the phone's local date; the server still validates.

/** Today's date (YYYY-MM-DD) in the given IANA timezone. */
export function todayInTimezone(timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" })
    .formatToParts(new Date())
    .reduce<Record<string, string>>((acc, p) => ({ ...acc, [p.type]: p.value }), {});
  return `${parts.year}-${parts.month}-${parts.day}`;
}

/** `isoDate` (YYYY-MM-DD) plus `days`: pure calendar arithmetic in UTC, unaffected by the phone's zone. */
export function addDaysToIsoDate(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** A Date whose *local* calendar fields equal the ISO date, for the native date picker. */
export function isoToPickerDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y!, m! - 1, d!);
}

/** The picker's selected local calendar date as YYYY-MM-DD. */
export function pickerDateToIso(date: Date): string {
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${mm}-${dd}`;
}
