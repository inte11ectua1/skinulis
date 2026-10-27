"""Импортируйте будущие модели здесь, чтобы Alembic видел их metadata."""

from app.models.base import Base
from app.models.group import Group, GroupMember
from app.models.identity_tokens import GroupInvite, TelegramLinkCode
from app.models.user import User

__all__ = ["Base", "User", "Group", "GroupMember", "GroupInvite", "TelegramLinkCode"]
