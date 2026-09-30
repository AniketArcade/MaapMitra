// Date math for the Schedule/Change date inputs. Always computed in the backend's
// scheduling timezone (ApplicationMeta.scheduling.timezone), never the browser's local date —
// the server is still the authority and validates independently.

/** Today's date (YYYY-MM-DD) in the given IANA timezone. */
export function todayInTimezone(timeZone: string): string {
  return new Date().toLocaleDateString("en-CA", { timeZone });
}

/** `isoDate` (YYYY-MM-DD) plus `days`, as a YYYY-MM-DD string. Pure calendar-date arithmetic:
 * parsed and re-formatted in UTC so it isn't shifted by the browser's own local timezone. */
export function addDaysToIsoDate(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
