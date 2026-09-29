"""Application and document categories.

ASSUMPTION: application types, document types and their requirements are MVP placeholders,
NOT the legal requirements under the Legal Metrology rules. Verify with a domain expert.
"""

from enum import StrEnum


class ApplicationType(StrEnum):
    VERIFICATION = "VERIFICATION"
    RE_VERIFICATION = "RE_VERIFICATION"


class ApplicationStatus(StrEnum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    SCHEDULED = "SCHEDULED"
    INSPECTION = "INSPECTION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CERTIFICATE_ISSUED = "CERTIFICATE_ISSUED"


TERMINAL_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {ApplicationStatus.REJECTED, ApplicationStatus.CERTIFICATE_ISSUED}
)


class DocumentType(StrEnum):
    PROOF_OF_OWNERSHIP = "PROOF_OF_OWNERSHIP"
    INSTRUMENT_PHOTO = "INSTRUMENT_PHOTO"
    PREVIOUS_CERTIFICATE = "PREVIOUS_CERTIFICATE"
    MODEL_APPROVAL = "MODEL_APPROVAL"
    OTHER = "OTHER"


APPLICATION_TYPE_LABELS: dict[ApplicationType, str] = {
    ApplicationType.VERIFICATION: "Verification",
    ApplicationType.RE_VERIFICATION: "Re-verification",
}

STATUS_LABELS: dict[ApplicationStatus, str] = {
    ApplicationStatus.DRAFT: "Draft",
    ApplicationStatus.SUBMITTED: "Submitted",
    ApplicationStatus.DOCUMENT_REVIEW: "Document review",
    ApplicationStatus.SCHEDULED: "Scheduled",
    ApplicationStatus.INSPECTION: "Inspection",
    ApplicationStatus.APPROVED: "Approved",
    ApplicationStatus.REJECTED: "Rejected",
    ApplicationStatus.CERTIFICATE_ISSUED: "Certificate issued",
}

DOCUMENT_LABELS: dict[DocumentType, str] = {
    DocumentType.PROOF_OF_OWNERSHIP: "Purchase invoice / proof of ownership",
    DocumentType.INSTRUMENT_PHOTO: "Photo of the instrument (nameplate visible)",
    DocumentType.PREVIOUS_CERTIFICATE: "Previous verification certificate",
    DocumentType.MODEL_APPROVAL: "Model approval certificate",
    DocumentType.OTHER: "Other supporting document",
}

REQUIREMENTS: dict[ApplicationType, frozenset[DocumentType]] = {
    ApplicationType.VERIFICATION: frozenset(
        {DocumentType.PROOF_OF_OWNERSHIP, DocumentType.INSTRUMENT_PHOTO}
    ),
    ApplicationType.RE_VERIFICATION: frozenset(
        {DocumentType.INSTRUMENT_PHOTO, DocumentType.PREVIOUS_CERTIFICATE}
    ),
}

MAX_FILE_BYTES = 10_485_760  # 10 MiB
MAX_UPLOAD_REQUEST_BYTES = MAX_FILE_BYTES + 65_536  # multipart overhead
MAX_DOCUMENTS = 10
ALLOWED_CONTENT_TYPES = ("application/pdf", "image/jpeg", "image/png")
