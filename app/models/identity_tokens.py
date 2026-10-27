"""Only digests of high-entropy invite/link secrets are persisted."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GroupInvite(Base):
    __tablename__ = "group_invites"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_group_invites"),
        ForeignKeyConstraint(
            ["group_id", "consumed_by"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_group_invites_consumer_membership",
            use_alter=True,
            deferrable=True,
            initially="DEFERRED",
        ),
        UniqueConstraint("token_hash", name="uq_group_invites_hash"),
        UniqueConstraint(
            "group_id", "client_request_id", name="uq_group_invites_request"
        ),
        CheckConstraint("id > 0", name="ck_group_invites_id_positive"),
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_group_invites_hash"),
        CheckConstraint(
            "expires_at = created_at + interval '24 hours'", name="ck_group_invites_ttl"
        ),
        CheckConstraint(
            "(consumed_at IS NULL) = (consumed_by IS NULL)",
            name="ck_group_invites_consumption",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR (revoked_at IS NULL AND consumed_at >= created_at AND consumed_at < expires_at)",
            name="ck_group_invites_consumed_time",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_group_invites_revoked_time",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", name="fk_group_invites_group", ondelete="RESTRICT"),
    )
    client_request_id: Mapped[UUID] = mapped_column(Uuid)
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_by: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", name="fk_group_invites_consumer", ondelete="RESTRICT"),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TelegramLinkCode(Base):
    __tablename__ = "telegram_link_codes"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_telegram_link_codes"),
        UniqueConstraint("token_hash", name="uq_telegram_link_codes_hash"),
        CheckConstraint("id > 0", name="ck_telegram_link_codes_id_positive"),
        CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name="ck_telegram_link_codes_hash"
        ),
        CheckConstraint(
            "expires_at = created_at + interval '10 minutes'",
            name="ck_telegram_link_codes_ttl",
        ),
        CheckConstraint(
            "consumed_at IS NULL OR (revoked_at IS NULL AND consumed_at >= created_at AND consumed_at < expires_at)",
            name="ck_telegram_link_codes_consumed_time",
        ),
        CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_telegram_link_codes_revoked_time",
        ),
        Index("ix_telegram_link_codes_user", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", name="fk_telegram_link_codes_user", ondelete="RESTRICT"),
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
