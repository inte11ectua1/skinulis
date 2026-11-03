"""Shared semantic button vocabulary; Unicode labels work without color or Premium."""

from dataclasses import dataclass
from typing import Literal

Style = Literal["primary", "success", "danger"]


@dataclass(frozen=True)
class ButtonTheme:
    icon: str
    style: Style | None = None


LABELS = {
    "home": "Главное меню",
    "groups": "Мои группы",
    "profile": "Профиль",
    "create": "Создать группу",
    "pending": "Ожидают подтверждения",
    "help": "Помощь",
    "cancel": "Отмена ввода",
}

THEMES = {
    "home": ButtonTheme("🏠"),
    "groups": ButtonTheme("👥"),
    "create": ButtonTheme("🆕", "primary"),
    "profile": ButtonTheme("👤"),
    "edit": ButtonTheme("✏️"),
    "help": ButtonTheme("❓"),
    "new_expense": ButtonTheme("➕", "primary"),
    "expenses": ButtonTheme("🧾"),
    "balances": ButtonTheme("💰"),
    "plan": ButtonTheme("🧭"),
    "transfers": ButtonTheme("🔄"),
    "mark_transfer": ButtonTheme("💸", "primary"),
    "history": ButtonTheme("📋"),
    "pending": ButtonTheme("⏳"),
    "back": ButtonTheme("↩️"),
    "next": ButtonTheme("➡️"),
    "refresh": ButtonTheme("🔃"),
    "invite": ButtonTheme("🔗", "primary"),
    "confirm": ButtonTheme("✅", "success"),
    "delete": ButtonTheme("🗑", "danger"),
    "reject": ButtonTheme("🚫", "danger"),
    "cancel": ButtonTheme("❌"),
    "preview": ButtonTheme("🔎", "primary"),
    "choose": ButtonTheme("☑️"),
    "none": ButtonTheme("▫️"),
    "done": ButtonTheme("✅", "primary"),
    "equal": ButtonTheme("⚖️"),
    "custom": ButtonTheme("🎯"),
    "receipt": ButtonTheme("🧾"),
    "filter": ButtonTheme("⚙️"),
    "open": ButtonTheme("📄"),
    "retry": ButtonTheme("🔃"),
    "person": ButtonTheme("👤"),
}
# Only presentation prefixes; never applied to user-generated names by the renderer.
PREFIXES = tuple(t.icon for t in THEMES.values()) + ("←", "＋", "💰", "✅", "☐")


def plain_label(label: str) -> str:
    """Test/operator label lookup, also accepts the previous vocabulary."""
    for _ in range(2):
        found = next((p for p in PREFIXES if label.startswith(p + " ")), None)
        if found is None:
            break
        label = label[len(found) :].lstrip()
    return label


def theme_for(label: str, action: str) -> str:
    text = plain_label(label)
    if action.startswith("st:receiver:"):
        return "person"
    if action.startswith(("st:detail:", "ex:detail:")):
        return "open"
    if text.startswith(
        ("Назад", "К ", "В группу", "Не менять", "Не вступать", "Продолжить ввод")
    ):
        return "back"
    if text in {"Обновить", "Обновить расход"}:
        return "refresh"
    if text.startswith(("Далее", "Продолжить →", "Следующая страница")):
        return "next"
    if action in {"home", "ui:cancel"}:
        return "home" if action == "home" else "cancel"
    if action.startswith(("groups:", "group:", "menu:groups")):
        return "groups"
    if action in {"profile", "menu:profile"}:
        return "profile"
    if action == "profile:rename":
        return "edit"
    if action in {"help", "menu:help"}:
        return "help"
    if action in {"create", "menu:create", "consent"}:
        return "create"
    if action in {"bootstrap", "join", "save_group", "save_invite", "ex:save"}:
        return "confirm"
    if action in {"decline", "ex:cancel"} or "discard:" in action:
        return "cancel"
    if action.startswith(("revoke:", "do_revoke", "ex:delete", "ex:remove")):
        return "delete"
    if action.startswith(("invites:", "issue:", "link")):
        return "invite"
    if action.startswith("members:"):
        return "person"
    if action.startswith("ex:new:"):
        return "new_expense"
    if action.startswith("ex:mode:"):
        return {"equal": "equal", "custom": "custom", "by_items": "receipt"}[
            action.rsplit(":", 1)[1]
        ]
    if action == "ex:all":
        return "choose"
    if action == "ex:none":
        return "none"
    if action == "ex:selected":
        return "done"
    if action == "ex:review":
        return "edit" if text.startswith("Исправить") else "back"
    if action == "ex:select":
        return "person"
    if action == "ex:preview":
        return "preview"
    if action.startswith(("ex:list:", "ex:receipt:", "ex:preview_details")):
        return "expenses"
    if action.startswith("ex:detail:"):
        return "open"
    if action.startswith(
        ("ex:edit", "ex:share", "ex:title", "ex:amount", "ex:modes", "ex:item:")
    ):
        return "edit"
    if action.startswith("st:balances:"):
        return "balances"
    if action.startswith("st:plan:"):
        return "plan"
    if (
        action.startswith(("st:groups:", "menu:pending"))
        or ":pending:incoming:" in action
    ):
        return "pending"
    if action.startswith("st:filters:"):
        return "filter"
    if action.startswith("st:list:"):
        return "history" if text == "История переводов" else "transfers"
    if action.startswith("st:new:"):
        return "mark_transfer"
    if action.startswith("st:receiver:"):
        return "person"
    if action == "st:resolve" or action.startswith("st:ask:"):
        return (
            "delete"
            if "отменить" in text.lower()
            else "reject"
            if "отклонить" in text.lower()
            else "confirm"
        )
    if action == "st:create":
        return "confirm"
    if "retry" in action or text.startswith(("Повторить", "Проверить")):
        return "retry"
    return "back" if "back" in action else "open"


def decorate(label: str, action: str) -> tuple[str, Style | None]:
    if action.startswith("ex:toggle:"):
        return label, None  # Selected/unselected mark is the semantic icon.
    theme = THEMES[theme_for(label, action)]
    # Preserve dynamic group/person/record names verbatim, including their emoji.
    dynamic = action.startswith(("st:receiver:", "st:detail:", "ex:detail:")) or (
        action.startswith("group:") and theme.icon == THEMES["groups"].icon
    )
    style = None if action.startswith("revoke:") else theme.style
    return theme.icon + " " + (label if dynamic else plain_label(label)), style
