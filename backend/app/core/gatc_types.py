from enum import StrEnum

# Spec 15: which role actually performed an inspection assignment. A new sibling module (mirrors
# core/verification_types.py's own reasoning, spec 14 D3): this is a narrow, two-value concept
# that doesn't fit core/application_types.py (application/document lifecycle vocab) or
# core/roles.py (the caller's own account role, five values, used for RBAC everywhere) — it's a
# *denormalized snapshot* of "which of the two roles capable of running an inspection did this
# one", stored on Inspection, not a general-purpose role.
#
# Real Postgres Enum type, not a CHECK-constrained Text column: every other small, closed-value
# column in this codebase (ChecklistResult, VerificationMode, PaymentStatus, OrgType, Role itself)
# uses `Enum(...)`, never a CHECK-constraint-mimicked enum. CheckConstraint in this codebase is
# reserved for cross-field/format invariants (state_code's regex, org_matches_role, capacity > 0),
# never for restricting a single column to a small fixed set of strings — that job already has an
# established, consistent tool here.


class InspectionAssigneeRole(StrEnum):
    LM_OFFICER = "LM_OFFICER"
    GATC = "GATC"
