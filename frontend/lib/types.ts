// Mirrors backend/app/schemas. Keep in sync.

export type Role =
  | "SUPER_ADMIN"
  | "STATE_ADMIN"
  | "DISTRICT_ADMIN"
  | "LM_OFFICER"
  | "GATC"
  | "BUSINESS";

export const ADMIN_ROLES: readonly Role[] = ["SUPER_ADMIN", "STATE_ADMIN", "DISTRICT_ADMIN"];

export type User = {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  organization_id: string | null;
  organization_name: string | null;
  state_code: string | null;
  district_code: string | null;
  is_active: boolean;
};

export type AuthResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
};

export type RegisterRequest = {
  organization_name: string;
  registration_number?: string;
  address?: string;
  state_code: string;
  district_code: string;
  full_name: string;
  email: string;
  phone?: string;
  password: string;
};

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

// Types, units, accuracy classes and regions are plain strings: the backend owns the values
// and serves them from GET /instruments/meta. Never hard-code them here.
export type Instrument = {
  id: string;
  instrument_uid: string;
  organization_id: string;
  organization_name: string;
  instrument_type: string;
  manufacturer: string;
  model: string;
  serial_number: string;
  capacity: number;
  capacity_unit: string;
  accuracy_class: string | null;
  // Spec 16: optional richer category system, additive alongside instrument_type/capacity/
  // capacity_unit/accuracy_class above. Both null together, or both set together (see
  // backend/app/schemas/instrument.py's category_pair_valid).
  category_id: number | null;
  category_values: Record<string, unknown> | null;
  // Spec 14: "Can the instrument be transported?" true -> Office/test centre verification,
  // false -> On-site (in-situ). Snapshotted onto Application.verification_mode at application
  // creation time (see verification_mode below) and never re-derived after that.
  transportable: boolean;
  address: string;
  state_code: string;
  district_code: string;
  latitude: number | null;
  longitude: number | null;
  created_at: string;
  updated_at: string;
  active_application: ActiveApplicationRef | null;
  // Fields the backend refuses to PATCH right now (identity fields while any application is
  // active; address/latitude/longitude too once an inspection is scheduled). Never re-derive
  // this rule client-side — disable exactly what's listed here (spec 05 D10).
  locked_fields: string[];
};

// Spec 16: one field definition inside an InstrumentCategory's `field_schema` (GET
// /instruments/meta's `categories`). Mirrors backend/app/schemas/instrument_category.py's
// CategoryFieldSchema field-for-field (snake_case JSON, same as the rest of this backend).
// `type` mirrors the backend's own deliberate choice to leave it a plain string rather than a
// union type enforced here — the set of valid values is documented, not type-checked, because
// the content lives in DB rows (JSONB), not code.
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

export type CategoryFieldOption = { value: string; label: string };

export type CategoryFieldSchema = {
  key: string;
  label: string;
  type: CategoryFieldType;
  required: boolean;
  unit: string | null;
  unit_options: string[] | null;
  options: CategoryFieldOption[] | null;
  presets: CategoryFieldOption[] | null;
  repeater_label: string | null;
  repeater_fields: CategoryFieldSchema[] | null;
  min: number | null;
  max: number | null;
  help_text: string | null;
};

// Mirrors backend/app/schemas/instrument_category.py's InstrumentCategoryOut.
export type InstrumentCategory = {
  id: number;
  name: string;
  validity_months: number;
  field_schema: CategoryFieldSchema[];
};

export type RegionMeta = {
  state_code: string;
  state_name: string;
  districts: { code: string; name: string }[];
};

export type InstrumentMeta = {
  types: { value: string; label: string; units: string[] }[];
  accuracy_classes: string[];
  regions: RegionMeta[];
  // Spec 16: the 33 instrument categories. Never hard-code their names/fields — load them from
  // here (getInstrumentMeta()) same as types/regions/accuracy_classes above.
  categories: InstrumentCategory[];
};

export type ActiveApplicationRef = { id: string; application_number: string; status: string };

export type InstrumentSummary = {
  id: string;
  instrument_uid: string;
  instrument_type: string;
  manufacturer: string;
  model: string;
  serial_number: string;
  capacity: number;
  capacity_unit: string;
};

// Statuses, application types and document types are strings owned by the backend
// (GET /applications/meta). Never hard-code their lists here.
export type Application = {
  id: string;
  application_number: string;
  status: string;
  application_type: string;
  instrument: InstrumentSummary;
  organization_id: string;
  organization_name: string;
  state_code: string;
  district_code: string;
  // Spec 14: raw enum ("OFFICE_TEST_CENTRE" | "ON_SITE"), snapshotted from the instrument's
  // transportable at application creation. Null for applications created before this feature
  // shipped. Labels come from ApplicationMeta.verification_modes — never hardcode them.
  verification_mode: string | null;
  business_notes: string | null;
  submitted_at: string | null;
  scheduled_date: string | null;
  created_at: string;
  updated_at: string;
};

export type DocumentOut = {
  id: string;
  document_type: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
};

export type Inspection = {
  id: string;
  scheduled_date: string;
  assigned_officer_name: string;
  // Spec 15: which of the two assignable roles actually performed this assignment. Raw enum
  // ("LM_OFFICER" | "GATC") — a small, self-evident, model-owned enum with no meta-exposed label
  // dict (mirrors ChecklistResult's own precedent), so display labels are fine to compute inline.
  assignee_role: string;
  submitted_at: string | null;
  checklist_summary: { passed: number; failed: number; na: number } | null;
};

export type Certificate = {
  id: string;
  application_id: string;
  certificate_number: string;
  status: string;
  valid_from: string;
  valid_until: string;
  issued_at: string;
  instrument_uid: string;
  instrument_type: string;
  manufacturer: string;
  model: string;
  serial_number: string;
  capacity: number;
  capacity_unit: string;
  organization_name: string;
  qr_code_data_uri: string;
  // Spec 13: self-referential supersede chain (raw ids; resolve via GET /certificates/{id} when
  // needed, matching this schema's existing flat-id convention) and a computed "expiring within
  // the reminder window" flag. supersedes_certificate_id/superseded_by_certificate_id are null
  // for a certificate that hasn't superseded, or been superseded by, another one.
  supersedes_certificate_id: string | null;
  superseded_by_certificate_id: string | null;
  is_expiring_soon: boolean;
};

export type VerifyResult = {
  certificate_number: string;
  status: string;
  instrument_type_label: string;
  // Spec 13: the instrument's own permanent public identifier — not owner PII, not an internal
  // database id (already printed on the certificate PDF anyone with the certificate number can
  // reach). Added to PublicVerifyOut alongside issued_by below; never add anything else here
  // without checking docs/specs/13-certificate-superseding.md §5 D4 first.
  instrument_uid: string;
  manufacturer: string;
  model: string;
  serial_number: string;
  valid_from: string;
  valid_until: string;
  // Spec 13: display label for the approving officer (Certificate.snapshot.approved_by_name).
  issued_by: string;
};

export type AdminCertificateStats = {
  valid: number; // includes valid-and-expiring-soon; not a disjoint bucket
  expiring_soon: number;
  expired: number;
  revoked: number;
};

// Spec 12: nested on ApplicationDetail.payment only — null until POST .../mock-pay is first
// called (the row is created lazily), informational only, never gates any transition.
export type Payment = {
  status: string; // NOT_PAID | PENDING | PAID — label via ApplicationMeta.payment_statuses
  amount: string | null;
  paid_at: string | null;
};

// Spec 11: one row of the document-review checklist snapshot, in template order.
export type ReviewChecklistItem = {
  item_key: string;
  label: string;
  checked: boolean;
};

export type ApplicationDetail = Application & {
  documents: DocumentOut[];
  history: {
    from_status: string | null;
    to_status: string;
    actor_name: string;
    note: string | null;
    created_at: string;
  }[];
  requirements: { document_type: string; label: string; required: boolean; satisfied: boolean }[];
  allowed_actions: string[];
  inspection: Inspection | null;
  certificate: Certificate | null;
  payment: Payment | null;
  can_reschedule: boolean;
  review_checklist: ReviewChecklistItem[];
};

// Spec 15: one GATC organization eligible for a given instrument category (GET
// /gatc/eligible?category_id=), for the scheduling officer's allocation dropdown.
export type GatcEligibleOrg = {
  id: string;
  name: string;
  state_code: string;
  district_code: string;
};

// Spec 15: one GATC-role user of an organization (GET /gatc/{organization_id}/users), for
// picking the specific person to assign alongside the organization.
export type GatcOrgUser = {
  id: string;
  full_name: string;
  email: string;
};

export type ApplicationStats = { total: number; by_status: Record<string, number> };

export type LabelledValue = { value: string; label: string };

export type ApplicationMeta = {
  application_types: (LabelledValue & { required_documents: string[] })[];
  statuses: LabelledValue[];
  document_types: LabelledValue[];
  limits: { max_file_bytes: number; max_documents: number; allowed_content_types: string[] };
  scheduling: { timezone: string; max_days_ahead: number };
  // Spec 11: the document-review checklist template — never hardcode item keys/labels client-side.
  document_review_checklist: { key: string; label: string }[];
  // Spec 14: display labels for Application.verification_mode ("OFFICE_TEST_CENTRE" | "ON_SITE").
  verification_modes: LabelledValue[];
  // Spec 12: display labels for Payment.status ("NOT_PAID" | "PENDING" | "PAID").
  payment_statuses: LabelledValue[];
};

// Checklist/measurement results and templates are backend-owned (GET /inspections/meta).
export type ChecklistResult = "PASS" | "FAIL" | "NA";

export type ChecklistItemOut = {
  item_key: string;
  label: string;
  result: ChecklistResult | null;
  remarks: string | null;
};

export type MeasurementOut = {
  label: string;
  unit: string;
  expected_value: number;
  observed_value: number | null;
};

export type InspectionDetail = {
  id: string;
  application_id: string;
  scheduled_date: string;
  assigned_officer_name: string;
  checklist_items: ChecklistItemOut[];
  measurements: MeasurementOut[];
  evidence: DocumentOut[];
  overall_remarks: string | null;
  submitted_at: string | null;
  can_edit: boolean;
};

export type InspectionMeta = {
  checklist_templates: Record<string, { key: string; label: string }[]>;
  measurement_labels: Record<string, string[]>;
  max_evidence_photos: number;
};

// Spec 17: Super Admin page. Mirrors backend/app/schemas/user.py's UserListOut — pending_cases/
// completed_cases are populated only when GET /users is called with ?role=LM_OFFICER (the LMO
// directory); null otherwise, never 0 (0 means "no cases," null means "not requested").
export type AdminUser = User & {
  pending_cases: number | null;
  completed_cases: number | null;
};

// Mirrors backend/app/schemas/audit.py's AuditLogOut. actor_name is null for a system actor
// (e.g. the expiry job) — render "System", not a blank.
export type AuditLogEntry = {
  id: string;
  actor_user_id: string | null;
  actor_name: string | null;
  action: string;
  entity_type: string | null;
  entity_id: string | null;
  organization_id: string | null;
  details: Record<string, unknown>;
  ip_address: string | null;
  created_at: string;
};

// Mirrors backend/app/schemas/organization.py's GatcDirectoryUserOut/GatcDirectoryOut.
export type GatcDirectoryUser = {
  id: string;
  full_name: string;
  email: string;
  is_active: boolean;
};

export type GatcDirectoryEntry = {
  id: string;
  name: string;
  state_code: string;
  district_code: string;
  eligible_categories: string[];
  pending_cases: number;
  completed_cases: number;
  // True iff >=1 active GATC-role user belongs to this org — a roll-up, not a real column
  // (Organization has no is_active of its own). Activate/Deactivate always targets a specific
  // user in `users`, never this org-level field directly.
  active: boolean;
  users: GatcDirectoryUser[];
};

// Mirrors backend/app/schemas/admin.py's StateOverviewRow.
export type StateOverviewRow = {
  state_code: string;
  state_name: string;
  instrument_count: number;
  pending_applications: number;
  certs_valid: number;
  certs_expired: number;
};

// Mirrors backend/app/schemas/admin.py's DistrictOverviewRow (spec 18) — the district-level
// sibling of StateOverviewRow, one state at a time.
export type DistrictOverviewRow = {
  state_code: string;
  district_code: string;
  district_name: string;
  instrument_count: number;
  pending_applications: number;
  certs_valid: number;
  certs_expired: number;
};

// Mirrors backend/app/schemas/user.py's UserCreate (officials only — BUSINESS self-registers,
// GATC is provisioned outside this form, see spec 17 D2).
export type CreateUserRequest = {
  email: string;
  full_name: string;
  phone?: string;
  role: "STATE_ADMIN" | "DISTRICT_ADMIN" | "LM_OFFICER";
  password: string;
  state_code: string;
  district_code?: string;
};
