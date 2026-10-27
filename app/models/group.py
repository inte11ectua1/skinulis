"""Identity groups. Composite membership is a stable future financial FK target."""

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
    SmallInteger,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Group(Base):
    __tablename__ = "groups"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_groups"),
        CheckConstraint("id > 0", name="ck_groups_id_positive"),
        CheckConstraint("length(name) BETWEEN 1 AND 120", name="ck_groups_name_length"),
        UniqueConstraint("owner_id", "client_request_id", name="uq_groups_request"),
        ForeignKeyConstraint(
            ["id", "owner_id"],
            ["group_members.group_id", "group_members.user_id"],
            name="fk_groups_owner_membership",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", name="fk_groups_owner", ondelete="RESTRICT")
    )
    name: Mapped[str] = mapped_column(String(120))
    client_request_id: Mapped[UUID] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        PrimaryKeyConstraint("group_id", "user_id", name="pk_group_members"),
        UniqueConstraint("group_id", "slot", name="uq_group_members_slot"),
        CheckConstraint("slot BETWEEN 1 AND 30", name="ck_group_members_slot"),
        Index("ix_group_members_user_group", "user_id", "group_id"),
    )

    group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("groups.id", name="fk_group_members_group", ondelete="RESTRICT"),
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", name="fk_group_members_user", ondelete="RESTRICT"),
    )
    slot: Mapped[int] = mapped_column(SmallInteger)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
