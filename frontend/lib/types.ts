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
  address: string;
  state_code: string;
  district_code: string;
  latitude: number | null;
  longitude: number | null;
  created_at: string;
  updated_at: string;
  active_application: ActiveApplicationRef | null;
};

export type InstrumentMeta = {
  types: { value: string; label: string; units: string[] }[];
  accuracy_classes: string[];
  regions: {
    state_code: string;
    state_name: string;
    districts: { code: string; name: string }[];
  }[];
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
  business_notes: string | null;
  submitted_at: string | null;
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
};

export type ApplicationStats = { total: number; by_status: Record<string, number> };

export type LabelledValue = { value: string; label: string };

export type ApplicationMeta = {
  application_types: (LabelledValue & { required_documents: string[] })[];
  statuses: LabelledValue[];
  document_types: LabelledValue[];
  limits: { max_file_bytes: number; max_documents: number; allowed_content_types: string[] };
};
