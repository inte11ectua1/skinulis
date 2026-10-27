"""Identity shared by API and future Telegram accounts; FK target: users.id."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Identity,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        PrimaryKeyConstraint(name="pk_users"),
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
        CheckConstraint("id > 0", name="ck_users_id_positive"),
        CheckConstraint("telegram_id > 0", name="ck_users_telegram_id_positive"),
        CheckConstraint(
            "email IS NOT NULL OR telegram_id IS NOT NULL",
            name="ck_users_identity_present",
        ),
        CheckConstraint(
            "(email IS NULL) = (password_hash IS NULL)",
            name="ck_users_email_password_pair",
        ),
        CheckConstraint(
            "email IS NULL OR (length(email) BETWEEN 3 AND 254 "
            "AND email = lower(email) AND email = btrim(email) "
            "AND email !~ '[[:space:]]' AND email !~ '[^ -~]')",
            name="ck_users_email_normalized",
        ),
        CheckConstraint(
            "password_hash IS NULL OR password_hash LIKE '$argon2id$%'",
            name="ck_users_password_argon2id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(254))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
