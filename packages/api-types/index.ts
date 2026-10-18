// Friendly names over the generated OpenAPI types. Regenerate with `npm run gen` (see README.md).
import type { components } from "./schema";

type S = components["schemas"];

export type { components, paths, operations } from "./schema";

export type Role = S["Role"];
export type User = S["UserOut"];
export type AuthResponse = S["AuthResponse"];
export type LoginRequest = S["LoginRequest"];
export type RegisterRequest = S["RegisterRequest"];
export type RefreshRequest = S["RefreshRequest"];

export type Instrument = S["InstrumentOut"];
export type InstrumentSummary = S["InstrumentSummary"];
export type InstrumentMeta = S["InstrumentMeta"];
export type InstrumentCategory = S["InstrumentCategoryOut"];
export type CategoryFieldSchema = S["CategoryFieldSchema"];
export type CategoryFieldOption = S["CategoryFieldOption"];
export type RegionMeta = S["RegionMeta"];
export type ActiveApplicationRef = S["ActiveApplicationRef"];

export type Application = S["ApplicationOut"];
export type ApplicationDetail = S["ApplicationDetail"];
export type ApplicationMeta = S["ApplicationMeta"];
export type ApplicationStats = S["ApplicationStats"];
export type DocumentOut = S["DocumentOut"];
export type Payment = S["PaymentOut"];
export type ReviewChecklistItem = S["ReviewChecklistItemOut"];
export type LabelledValue = S["LabelledValue"];

export type Inspection = S["InspectionOut"];
export type InspectionDetail = S["InspectionDetail"];
export type InspectionMeta = S["InspectionMeta"];
export type ChecklistItemOut = S["ChecklistItemOut"];
export type MeasurementOut = S["MeasurementOut"];
export type ChecklistResult = S["ChecklistResult"];

export type Certificate = S["CertificateOut"];
export type VerifyResult = S["PublicVerifyOut"];
export type AdminCertificateStats = S["AdminCertificateStats"];

export type GatcEligibleOrg = S["GatcEligibleOrgOut"];
export type GatcOrgUser = S["GatcOrgUserOut"];
export type GatcDirectoryUser = S["GatcDirectoryUserOut"];
export type GatcDirectoryEntry = S["GatcDirectoryOut"];

export type AdminUser = S["UserListOut"];
export type AuditLogEntry = S["AuditLogOut"];
export type StateOverviewRow = S["StateOverviewRow"];
export type DistrictOverviewRow = S["DistrictOverviewRow"];
export type CreateUserRequest = S["UserCreate"];

export type Page<T> = { items: T[]; total: number; page: number; page_size: number };
