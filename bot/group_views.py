"""L-03 group_views; approved T-06 API only."""

from datetime import UTC, datetime
from uuid import uuid4

from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from pydantic import ValidationError

from bot.api_client import ApiError, BotApi
from bot.dto import GroupDraft, GroupProfile, Page
from bot.presentation import person, roster
from bot.states import GroupFlow, Navigation
from bot.ui import UNCERTAIN, reset, safe_error, screen


def paging[T](page: Page[T], prefix: str) -> list[tuple[str, str]]:
    actions = [("Обновить", f"{prefix}:0")]
    if page.offset:
        actions.append(
            ("Назад по списку", f"{prefix}:{max(0, page.offset - page.limit)}")
        )
    if len(page.items) == page.limit:
        actions.append(("Далее", f"{prefix}:{page.offset + page.limit}"))
    return actions


async def show_groups(
    message: Message, state: FSMContext, api: BotApi, actor: int, offset: int = 0
) -> None:
    page = await api.groups(actor, offset=offset)
    await state.set_state(Navigation.menu)
    actions = [(g.name[:60], f"group:{g.id}") for g in page.items]
    actions += paging(page, "groups") + [
        ("Создать группу", "create"),
        ("Главное меню", "home"),
    ]
    text = (
        "Ваши группы"
        if page.items
        else (
            "У вас пока нет групп. Попросите владельца прислать приглашение."
            if not offset
            else "На этой странице групп нет. Вернитесь назад или обновите список."
        )
    )
    await screen(message, state, text, actions)


async def show_group(
    message: Message, state: FSMContext, api: BotApi, actor: int, group: GroupProfile
) -> None:
    profile = await api.profile(actor)
    members = await api.members(actor, group.id)
    names = await roster(api, actor, group.id, first=members)
    text = f"{group.name}\nОбщие расходы вашей компании\n\n" + "\n".join(
        person(names, m.user_id)
        + (" · вы" if m.user_id == profile.id else "")
        + (" · владелец" if m.is_owner else "")
        for m in members.items
    )
    actions = [
        ("＋ Добавить расход", f"ex:new:{group.id}"),
        ("💰 Кто кому должен", f"st:balances:{group.id}"),
        ("План переводов", f"st:plan:{group.id}"),
        ("Расходы", f"ex:list:{group.id}:0"),
        ("Переводы", f"st:list:{group.id}:all:all:0"),
        ("Участники", f"members:{group.id}:0"),
        ("← Мои группы", "groups:0"),
    ]
    if profile.id == group.owner_id:
        actions.insert(-1, ("Пригласить друзей", f"invites:{group.id}:0"))
    await state.set_state(Navigation.menu)
    await screen(message, state, text, actions)


async def show_invites(
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    group_id: int,
    offset: int = 0,
) -> None:
    page = await api.invites(actor, group_id, offset=offset)
    text = "Пригласить друзей\nОдна ссылка — один человек. Действует сутки.\n\n"
    actions: list[tuple[str, str]] = []
    for index, invite in enumerate(page.items):
        status = (
            "использовано"
            if invite.consumed_at
            else "отозвано"
            if invite.revoked_at
            else "истекло"
            if invite.expires_at <= datetime.now(UTC)
            else "можно использовать"
        )
        text += f"Ссылка {page.offset + index + 1} · {status}\n"
        if not invite.consumed_at and not invite.revoked_at:
            actions.append(
                (
                    f"Отозвать ссылку {page.offset + index + 1}",
                    f"revoke:{group_id}:{invite.id}",
                )
            )
    if not page.items:
        text += "На этой странице приглашений нет.\n"
    actions += paging(page, f"invites:{group_id}") + [
        ("Создать приглашение", f"issue:{group_id}"),
        ("К группе", f"group:{group_id}"),
    ]
    await state.set_state(Navigation.menu)
    await screen(message, state, text, actions)


async def recover_invite(
    message: Message, state: FSMContext, api: BotApi, actor: int, offset: int = 0
) -> None:
    data = await state.get_data()
    group_id = int(data["group_id"])
    await state.set_state(GroupFlow.invite_uncertain)
    try:
        page = await api.invites(actor, group_id, offset=offset)
    except ApiError as error:
        await screen(
            message,
            state,
            UNCERTAIN + " " + safe_error(error),
            [("Проверить приглашения", f"recover:{offset}")],
        )
        return
    found = next(
        (i for i in page.items if str(i.client_request_id) == data["request_key"]), None
    )
    actions = [("Проверить с начала", "recover:0")]
    if found:
        text = "Приглашение создано, но ссылка не сохранилась. Отзовите её перед созданием новой."
        if not found.consumed_at and not found.revoked_at:
            actions.append(
                ("Отозвать потерянное приглашение", f"revoke:{group_id}:{found.id}")
            )
        else:
            text += " Приглашение уже использовано или отозвано."
            actions = [("К приглашениям", f"invites:{group_id}:0")]
    else:
        text = "На проверенной странице запись не найдена. Результат выдачи остаётся неизвестным. Новую ссылку автоматически не создаём."
        if len(page.items) == page.limit:
            actions.append(
                ("Проверить следующую страницу", f"recover:{page.offset + page.limit}")
            )
    await state.set_state(GroupFlow.invite_uncertain)
    await screen(message, state, text, actions)


async def group_name(message: Message, state: FSMContext) -> None:
    try:
        draft = GroupDraft(name=message.text or "", client_request_id=uuid4())
    except ValidationError:
        await message.answer(
            "Название не подошло. Нужно от 1 до 120 символов без переносов и скрытых знаков."
        )
        return
    await state.update_data(draft=draft.model_dump_json())
    await state.set_state(GroupFlow.confirm)
    await screen(
        message,
        state,
        f"Создать группу «{draft.name}»? Вы станете владельцем и первым участником.",
        [
            ("Создать", "save_group"),
            ("Изменить название", "rename"),
            ("Отмена", "home"),
        ],
    )


async def begin_group(message: Message, state: FSMContext) -> None:
    await reset(state)
    await state.set_state(GroupFlow.name)
    await screen(
        message,
        state,
        "Новая группа\nКак назовём вашу компанию?\n\nНапример, «Поездка в Казань». До 120 символов.",
        [("← Назад", "home")],
    )
