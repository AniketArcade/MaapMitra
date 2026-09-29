import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, Text, true
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.roles import Role
from app.db.base import Base
from app.db.mixins import Timestamps, UUIDPk
from app.models.organization import Organization


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(role IN ('BUSINESS', 'GATC')) = (organization_id IS NOT NULL)",
            name="org_matches_role",
        ),
        CheckConstraint(
            "role <> 'STATE_ADMIN' OR state_code IS NOT NULL", name="state_admin_scope"
        ),
        CheckConstraint(
            "role NOT IN ('DISTRICT_ADMIN', 'LM_OFFICER') "
            "OR (state_code IS NOT NULL AND district_code IS NOT NULL)",
            name="district_scope",
        ),
    )

    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text)
    role: Mapped[Role] = mapped_column(Enum(Role, name="user_role"), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), index=True
    )
    state_code: Mapped[str | None] = mapped_column(Text)
    district_code: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization | None] = relationship(lazy="joined")
