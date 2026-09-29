import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel

from app.core.application_types import DocumentType
from app.models.document import Document


class DocumentOut(BaseModel):
    """Never includes storage_path or a URL: links come from GET /documents/{id}/url."""

    id: uuid.UUID
    document_type: DocumentType
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime

    @classmethod
    def from_model(cls, d: Document) -> Self:
        return cls(
            id=d.id,
            document_type=d.document_type,
            original_filename=d.original_filename,
            content_type=d.content_type,
            size_bytes=d.size_bytes,
            created_at=d.created_at,
        )


class DocumentUrl(BaseModel):
    url: str
    expires_in: int
