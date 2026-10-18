// API types are generated from the backend OpenAPI schema (packages/api-types, `npm run gen`).
// This file re-exports them under the names the app uses, plus UI-only helpers.
// Types, units, accuracy classes, regions, statuses are plain strings/unions from the backend:
// never hard-code their lists; load them via the /meta endpoints.
import type { Role } from "@api-types";

export type {
  ActiveApplicationRef,
  AdminCertificateStats,
  AdminUser,
  Application,
  ApplicationDetail,
  ApplicationMeta,
  ApplicationStats,
  AuditLogEntry,
  AuthResponse,
  CategoryFieldOption,
  CategoryFieldSchema,
  Certificate,
  ChecklistItemOut,
  ChecklistResult,
  CreateUserRequest,
  DistrictOverviewRow,
  DocumentOut,
  GatcDirectoryEntry,
  GatcDirectoryUser,
  GatcEligibleOrg,
  GatcOrgUser,
  Inspection,
  InspectionDetail,
  InspectionMeta,
  Instrument,
  InstrumentCategory,
  InstrumentMeta,
  InstrumentSummary,
  LabelledValue,
  MeasurementOut,
  Page,
  Payment,
  RegionMeta,
  RegisterRequest,
  ReviewChecklistItem,
  Role,
  StateOverviewRow,
  User,
  VerifyResult,
} from "@api-types";

export const ADMIN_ROLES: readonly Role[] = ["SUPER_ADMIN", "STATE_ADMIN", "DISTRICT_ADMIN"];

// Documented values of CategoryFieldSchema.type (the backend leaves it a free string: the content
// lives in DB rows, not code). Used by the dynamic category form to pick an input.
export type CategoryFieldType =
  | "text"
  | "number"
  | "select"
  | "multiselect"
  | "unit-number"
  | "range-band"
  | "repeater"
  | "toggle"
  | "date"
  | "file";
