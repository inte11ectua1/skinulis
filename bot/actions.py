"""L-03 actions; approved T-06 API only."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import LinkPreviewOptions, Message
from pydantic import SecretStr

from bot.api_client import ApiError, BotApi
from bot.dto import GroupDraft, valid_capability
from bot.group_views import (
    begin_group,
    paging,
    recover_invite,
    show_group,
    show_groups,
    show_invites,
)
from bot.presentation import person, roster
from bot.profile_views import begin_name, profile_screen
from bot.screen_lifecycle import retire
from bot.states import GroupFlow, Onboarding
from bot.ui import (
    HELP,
    UNCERTAIN,
    UNCERTAIN_KINDS,
    UNKNOWN,
    check_profile,
    home,
    offer_onboarding,
    ready,
    recover_identity,
    reset,
    safe_error,
    screen,
)


async def dispatch_action(
    action: str,
    message: Message,
    state: FSMContext,
    api: BotApi,
    actor: int,
    bot: Bot,
    data: dict[str, object],
    previous: str | None,
) -> None:
    if action == "home":
        await reset(state)
        await check_profile(message, state, api, actor)
    elif action == "profile":
        await profile_screen(message, state, api, actor)
    elif action == "profile:rename":
        await begin_name(message, state)
    elif action == "help":
        await screen(message, state, HELP, [("← Главное меню", "home")])
    elif action == "decline":
        await reset(state)
        await message.answer(
            "Профиль не создавали. Когда будете готовы, откройте /start."
        )
    elif action == "check":
        await check_profile(message, state, api, actor)
    elif action == "identity_recheck":
        await recover_identity(message, state, api, actor)
    elif action == "consent" and previous == Onboarding.choice.state:
        await state.set_state(Onboarding.consent)
        await screen(
            message,
            state,
            f"Создать профиль?\nИмя: {data.get('telegram_name', 'Участник')}\n\nЭто имя увидят участники ваших групп. Его можно изменить в профиле.\nПароль не нужен. Если вы уже регистрировались по почте, вернитесь и выберите привязку: объединить два профиля нельзя.",
            [("Да, создать", "bootstrap"), ("Назад", "onboard")],
        )
    elif action == "onboard":
        await offer_onboarding(message, state)
    elif action == "bootstrap" and previous == Onboarding.consent.state:
        await state.set_state(GroupFlow.busy)
        try:
            await api.bootstrap(actor, str(data.get("telegram_name", "Участник")))
        except ApiError as error:
            if error.kind in UNCERTAIN_KINDS:
                await message.answer(UNCERTAIN)
                await recover_identity(message, state, api, actor)
            else:
                await message.answer(safe_error(error))
                await offer_onboarding(message, state)
        else:
            await state.update_data(toast="Профиль создан.")
            await ready(message, state)
    elif action == "link" and previous == Onboarding.choice.state:
        await state.set_state(Onboarding.link_code)
        await screen(
            message,
            state,
            "Привязать аккаунт\nПолучите одноразовый код по инструкции подключения в своём аккаунте по почте.\n\nПришлите сюда только код. Он действует 10 минут. Пароль и ключ доступа не отправляйте.",
            [("Назад", "onboard")],
        )
    elif action in {"create", "rename"}:
        await begin_group(message, state)
    elif action == "save_group" and previous == GroupFlow.confirm.state:
        draft = GroupDraft.model_validate_json(str(data["draft"]))
        await state.set_state(GroupFlow.busy)
        try:
            group = await api.create_group(actor, draft)
        except ApiError as error:
            await state.set_state(GroupFlow.confirm)
            if error.kind in UNCERTAIN_KINDS:
                await screen(
                    message,
                    state,
                    UNCERTAIN
                    + " Можно безопасно повторить тот же запрос с теми же данными.",
                    [
                        ("Повторить тот же запрос", "save_group"),
                        ("Проверить мои группы", "groups:0"),
                    ],
                )
            else:
                await screen(
                    message,
                    state,
                    safe_error(error),
                    [("Проверить мои группы", "groups:0"), ("Отмена", "home")],
                )
        else:
            await reset(state)
            await state.update_data(toast="Группа создана.")
            await show_group(message, state, api, actor, group)
    elif action.startswith("groups:"):
        await show_groups(message, state, api, actor, int(action.split(":")[1]))
    elif action.startswith("group:"):
        await show_group(
            message,
            state,
            api,
            actor,
            await api.group(actor, int(action.split(":")[1])),
        )
    elif action.startswith("members:"):
        _, gid_text, offset_text = action.split(":")
        page = await api.members(actor, int(gid_text), offset=int(offset_text))
        names = await roster(api, actor, int(gid_text), first=page)
        viewer = await api.profile(actor)
        text = "Участники группы\n\n" + "\n".join(
            person(names, m.user_id)
            + (" · вы" if m.user_id == viewer.id else "")
            + (" · владелец" if m.is_owner else "")
            for m in page.items
        )
        if not page.items:
            text += "Здесь пока никого нет."
        text += "\n\nПри одинаковых именах сверяйте буквенную метку. Каждый видит пометку «вы» у себя."
        await screen(
            message,
            state,
            text,
            paging(page, f"members:{gid_text}") + [("К группе", f"group:{gid_text}")],
        )
    elif action.startswith("invites:"):
        _, gid_text, offset_text = action.split(":")
        await show_invites(message, state, api, actor, int(gid_text), int(offset_text))
    elif action.startswith("issue:"):
        gid = int(action.split(":")[1])
        await api.invites(actor, gid)  # owner checked by API, not cached FSM
        await state.update_data(group_id=gid, request_key=str(uuid4()))
        await state.set_state(GroupFlow.invite_confirm)
        await screen(
            message,
            state,
            "Создать одноразовое приглашение? Действует сутки. Ссылку получите только один раз; перешлите её одному человеку.",
            [("Создать приглашение", "save_invite"), ("К группе", f"group:{gid}")],
        )
    elif action == "save_invite" and previous == GroupFlow.invite_confirm.state:
        me = await bot.get_me()  # actual Telegram username, obtained BEFORE write
        if not me.username:
            await message.answer(
                "Не удалось определить имя бота. Приглашение не запрашивали. /cancel — вернуться."
            )
            return
        gid = int(str(data["group_id"]))
        await state.set_state(GroupFlow.busy)
        try:
            invite = await api.issue_invite(actor, gid, UUID(str(data["request_key"])))
        except ApiError as error:
            if error.kind in UNCERTAIN_KINDS:
                await message.answer(UNCERTAIN)
                await recover_invite(message, state, api, actor)
            else:
                await message.answer(safe_error(error))
                await show_invites(message, state, api, actor, gid)
        else:
            await retire(message, state)
            if invite.token is None:
                await message.answer(
                    "Ссылка уже была выдана и не сохранилась. Отзовите приглашение, затем создайте новое."
                )
            else:
                raw = invite.token.get_secret_value()
                if (
                    not valid_capability(raw)
                    or invite.revoked_at
                    or invite.consumed_at
                    or invite.expires_at <= datetime.now(UTC)
                ):
                    await message.answer(
                        "Ссылка не сохранилась. Проверьте приглашения и отзовите потерянное."
                    )
                else:
                    await message.answer(
                        f"Приглашение готово\nПерешлите ссылку одному другу. Она действует сутки и используется один раз.\n\nhttps://t.me/{me.username}?start=i_{raw}",
                        parse_mode=None,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    )
            await reset(state)
            await show_invites(message, state, api, actor, gid)
    elif action.startswith("recover:"):
        await recover_invite(message, state, api, actor, int(action.split(":")[1]))
    elif action.startswith("revoke:"):
        _, gid_text, iid_text = action.split(":")
        await state.update_data(group_id=int(gid_text), invite_id=int(iid_text))
        await state.set_state(GroupFlow.revoke_confirm)
        await screen(
            message,
            state,
            "Отозвать ссылку?\nВступить по ней больше не получится.",
            [("Да, отозвать", "do_revoke"), ("Отмена", f"invites:{gid_text}:0")],
        )
    elif action == "do_revoke" and previous == GroupFlow.revoke_confirm.state:
        gid, iid = int(str(data["group_id"])), int(str(data["invite_id"]))
        try:
            result = await api.revoke_invite(actor, gid, iid)
        except ApiError as error:
            if error.kind in UNCERTAIN_KINDS:
                await screen(
                    message,
                    state,
                    UNCERTAIN + " Повтор отзыва того же приглашения безопасен.",
                    [
                        ("Повторить отзыв", "do_revoke"),
                        ("Проверить приглашения", f"invites:{gid}:0"),
                    ],
                )
            else:
                await message.answer(safe_error(error))
                await show_invites(message, state, api, actor, gid)
        else:
            await state.update_data(
                toast="Ссылка отозвана."
                if result.revoked_at
                else "Отзыв не подтверждён. Обновите список приглашений."
            )
            await reset(state)
            await show_invites(message, state, api, actor, gid)
    elif action == "join" and previous == GroupFlow.join_confirm.state:
        token = data.get("invite")
        if not isinstance(token, SecretStr):
            await message.answer(UNKNOWN)
            return
        await reset(state)  # drop capability BEFORE send, no automatic join retry
        await state.set_state(GroupFlow.busy)
        try:
            group = await api.join(actor, token)
        except ApiError as error:
            if error.kind in UNCERTAIN_KINDS:
                await state.set_state(GroupFlow.join_uncertain)
                await message.answer(
                    UNCERTAIN
                    + " Автоматически повторять вступление нельзя. Проверяем доступные вам группы; список не доказывает результат именно этого запроса."
                )
                try:
                    await show_groups(message, state, api, actor)
                except ApiError:
                    await screen(
                        message,
                        state,
                        "Список пока недоступен. Результат вступления неизвестен.",
                        [("Проверить мои группы", "groups:0")],
                    )
            else:
                await message.answer(safe_error(error))
                await home(message, state)
        else:
            await state.update_data(toast="Вы в группе!")
            await show_group(message, state, api, actor, group)
    else:
        await message.answer(UNKNOWN)
