import uuid

from sqlalchemy import Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk


class DocumentReviewChecklistItem(UUIDPk, Timestamps, Base):
    """One row per DOCUMENT_REVIEW_CHECKLIST_TEMPLATE entry for an application (step 11),
    snapshotted when the application enters DOCUMENT_REVIEW (app/core/document_review_templates.py).
    If the application later cycles DOCUMENTS_DEFICIENT -> SUBMITTED -> DOCUMENT_REVIEW again,
    the existing rows are reset (checked=False), not recreated, so `item_key` stays unique per
    application across review rounds and a later template edit never changes an application
    already under review — mirroring inspection_checklist_items' snapshot rule (spec 06)."""

    __tablename__ = "document_review_checklist_items"
    __table_args__ = (UniqueConstraint("application_id", "item_key"),)

    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    item_key: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    checked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
