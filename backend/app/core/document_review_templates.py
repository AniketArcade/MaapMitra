"""Document-review checklist template (step 11 / spec `docs/specs/11-document-review-checklist.md`).

ASSUMPTION: this checklist is an illustrative demo aid for the officer's document-review step,
not a legally mandated checklist under the Legal Metrology Rules and not sourced from an actual
department SOP. Verify with a domain expert before any non-demo use — the same caveat
core/instrument_types.py, core/application_types.py and core/inspection_templates.py already
carry for their own categories. Fee/payment verification is deliberately excluded: payments are
mocked separately (root CLAUDE.md's "Payments: mocked in MVP" open decision) and are not part of
this checklist.

Unlike core/inspection_templates.py's CHECKLIST_TEMPLATES, this is a single generic list, not one
per InstrumentType: document review checks the submission as a whole (form, documents,
jurisdiction, identity match), not category-specific technical content — that remains the field
inspection's job.
"""

from typing import NamedTuple


class DocumentReviewItemDef(NamedTuple):
    key: str
    label: str


DOCUMENT_REVIEW_CHECKLIST_TEMPLATE: list[DocumentReviewItemDef] = [
    DocumentReviewItemDef("form_complete", "Application form complete and signed"),
    DocumentReviewItemDef(
        "identity_matches_registry",
        "Instrument identity (manufacturer, model, serial number) matches the registry",
    ),
    DocumentReviewItemDef(
        "documents_attached_legible", "All required documents attached and legible"
    ),
    DocumentReviewItemDef(
        "address_jurisdiction_complete",
        "Address and jurisdiction details complete and correct",
    ),
    DocumentReviewItemDef(
        "application_type_correct",
        "Application type correctly selected for the instrument's verification history",
    ),
    DocumentReviewItemDef(
        "previous_certificate_referenced",
        "Previous certificate, if any, correctly referenced and consistent",
    ),
    DocumentReviewItemDef(
        "photo_shows_nameplate", "Instrument photo clearly shows the nameplate/marking"
    ),
    DocumentReviewItemDef(
        "no_conflicting_application", "No duplicate or conflicting active application exists"
    ),
]
