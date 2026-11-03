"""Offline gallery of actual Dispatcher screens; no Telegram/network connections."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html import escape
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
from aiogram.types import InlineKeyboardMarkup

from bot.presentation import STATUSES
from tests.unit.test_bot_expenses import ExpenseServer, expense_journey
from tests.unit.test_bot_onboarding_groups import ContractFixture, journey
from tests.unit.test_bot_settlements import SettlementServer, settlement_journey

ROOT = Path(__file__).resolve().parents[1]
NAMES = {1: "Тимур", 10: "Тимур", 20: "Саша", 30: "Саша", 40: "Даша"}


@asynccontextmanager
async def example(fixture: Any) -> AsyncIterator[Any]:
    generator = fixture.__wrapped__()
    try:
        yield await anext(generator)
    finally:
        await generator.aclose()


def named(original: Any) -> Any:
    def respond(server: Any, request: httpx.Request) -> httpx.Response:
        response: httpx.Response = original(server, request)
        if request.url.path.endswith("/members") and response.status_code == 200:
            body = response.json()
            for member in body["items"]:
                member["display_name"] = NAMES.get(member["user_id"], "Друг")
            return httpx.Response(200, json=body)
        return response

    return respond


async def render() -> None:
    cards: list[str] = []

    def capture(title: str, j: Any) -> None:
        screen = j.ui.sent[-1]
        markup = screen.reply_markup
        keyboard = ""
        if isinstance(markup, InlineKeyboardMarkup):
            keyboard = "".join(
                '<div class="row">'
                + "".join(
                    '<span class="button">' + escape(b.text) + "</span>" for b in row
                )
                + "</div>"
                for row in markup.inline_keyboard
            )
        # Only renderer-generated <b>/escaped user text; never callback payloads.
        cards.append(
            "<article><h2>"
            + escape(title)
            + '</h2><div class="phone"><div class="bubble">'
            + screen.text.replace("\n", "<br>")
            + "</div>"
            + keyboard
            + "</div></article>"
        )

    with patch.object(ContractFixture, "respond", named(ContractFixture.respond)):
        async with example(journey) as j:
            await j.ui.send("/start")
            capture("01 · Первый запуск", j)
            await j.choose("Создать профиль")
            capture("02 · Явное согласие на имя", j)
            await j.choose("Да, создать")
            j.server.profile["display_name"] = "Тимур"
            capture("03 · Главное меню", j)
            await j.choose("👤 Профиль")
            capture("04 · Профиль", j)
            await j.choose("Изменить имя")
            capture("05 · Редактирование имени", j)
            await j.ui.send("Тимур")
            await j.choose("← Главное меню")
            await j.choose("Помощь")
            capture("06 · Помощь", j)
            await j.ui.click("menu:groups")
            capture("06b · Группы: пустое состояние", j)
            await j.open_group()
            capture("07 · Группа владельца", j)
            await j.choose("Участники")
            capture("07b · Участники", j)
            await j.choose("К группе")
            await j.choose("Пригласить друзей")
            capture("08 · Приглашения (пусто)", j)
            # No invite secret is rendered into this public gallery.
        async with example(journey) as j:
            await j.ui.send("/start")
            await j.choose("Привязать существующий аккаунт")
            capture("08b · Привязка прежнего профиля", j)

    with patch.object(ExpenseServer, "respond", named(ExpenseServer.respond)):
        async with example(expense_journey) as j:
            await j.start("equal")
            capture("09 · Название расхода", j)
            await j.choose("Назад")
            await j.choose("Сменить режим")
            capture("09b · Способы разделения", j)
            await j.choose("Поровну")
            await j.ui.send("Ужин в пятницу")
            capture("10 · Сумма", j)
            await j.ui.send("100.00")
            await j.choose("Выбрать всех")
            await j.choose("@ex:toggle:30")
            capture("11 · Выбор участников, 2 из 3", j)
            await j.choose("Выбрать всех")
            await j.choose("Готово")
            capture("12 · Черновик до серверного расчёта", j)
        async with example(expense_journey) as j:
            await j.start("custom")
            await j.ui.send("Общее такси")
            await j.ui.send("10.00")
            await j.choose("Выбрать всех")
            await j.choose("Готово")
            capture("12b · Указать суммы: ввод долей", j)
            for value in ["0.00", "3.33", "6.67"]:
                await j.ui.send(value)
            capture("12c · Указать суммы: черновик", j)
        async with example(expense_journey) as j:
            await j.simple()
            await j.choose("Проверить доли")
            capture("13 · Серверный предпросмотр: поровну", j)
            await j.choose("Подтвердить расход")
            capture("14 · Сохранённый расход", j)
            await j.choose("К расходам")
            capture("14b · Список расходов", j)
            await j.choose("@ex:detail:7")
            await j.choose("Удалить")
            capture("15 · Предупреждение об удалении", j)
        async with example(expense_journey) as j:
            await j.receipt()
            capture("16 · Чек перед расчётом", j)
            await j.choose("Проверить доли")
            capture("17 · Чек: итоговые доли", j)
            await j.choose("Позиции чека")
            capture("18 · Подробности чека", j)
        async with example(expense_journey) as j:
            await j.simple()
            await j.choose("Проверить доли")
            j.server.fail_after = "POST"
            await j.choose("Подтвердить расход")
            capture("18b · Потерянный ответ: безопасное восстановление", j)

    with patch.object(SettlementServer, "respond", named(SettlementServer.respond)):
        async with example(settlement_journey) as j:
            await j.group()
            await j.choose("💰 Кто кому должен")
            capture("19 · Балансы", j)
            await j.choose("План переводов")
            capture("20 · План переводов", j)
            await j.choose("История переводов")
            capture("21 · История (пусто)", j)
            await j.choose("Фильтры")
            capture("22 · Фильтры отдельно", j)
        async with example(settlement_journey) as j:
            await j.draft()
            capture("23 · Подтверждение внешнего перевода", j)
            await j.choose("Да, я уже перевёл деньги")
            capture("24 · Ожидает: отправитель", j)
        for status in ("pending", "confirmed", "rejected", "cancelled"):
            async with example(settlement_journey) as j:
                j.server.owner = 10
                await j.open(status)
                capture("25 · Получатель: " + STATUSES[status], j)

    before = (
        "<article><h2>До · Фрагмент карточки расхода</h2><div class=phone><div class=bubble>"
        "Расход: Ресторан<br>Группа #100<br>Плательщик: участник #10<br>Режим: По позициям<br>Всего: 3200.00 ₽ (API)<br>Итоговые доли API:<br>#10: 1000.00 ₽<br>#20: 1400.00 ₽<br>#30: 800.00 ₽"
        "</div></div></article><article><h2>До · Выбор участников</h2><div class=phone><div class=bubble>"
        "Кто участвует? Выберите хотя бы одного; плательщик может не участвовать."
        "</div><div class=row><span class=button>Участник #10</span></div>"
        "<div class=row><span class=button>Участник #20</span></div>"
        "<div class=row><span class=button>Участник #30</span></div>"
        "<div class=row><span class=button>Выбрать всех</span></div>"
        "<div class=row><span class=button>Готово</span></div>"
        "<div class=row><span class=button>Назад к черновику</span></div></div></article>"
    )
    style = """
:root{font-family:system-ui,sans-serif;color:#152f38;background:#eff4f3}
body{margin:0;padding:28px}header{max-width:980px;margin:0 auto 28px}
h1{font-size:30px}p{line-height:1.6}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px;max-width:1400px;margin:auto}
article{min-width:0}h2{font-size:17px;margin:0 0 12px}.phone{max-width:390px;padding:16px;background:#dfe9e5;border-radius:24px;border:1px solid #c8d8d1}
.bubble{background:white;border-radius:14px;padding:16px;line-height:1.5;overflow-wrap:anywhere;box-shadow:0 1px 2px #0001;margin-bottom:8px}
.row{display:flex;gap:6px;margin-top:5px}.button{flex:1;text-align:center;border-radius:8px;background:#4b7169;color:white;padding:10px 8px;font-size:14px}
code{background:white;padding:2px 5px}footer{margin:28px auto;max-width:980px}
"""
    output = ROOT / "docs/ux/84_SCREENS.html"
    output.write_text(
        '<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        + "<title>Скинулись · #84 · Реальные шаблоны</title><style>"
        + style
        + "</style><header><h1>Скинулись · офлайн-галерея #84</h1>"
        + "<p><b>Симуляция, не скриншоты Telegram.</b> Текст и кнопки получены из настоящего Dispatcher/FSM; HTTP и Telegram замоканы. Синтетические данные. Цвета галереи не задают цвета Telegram.</p>"
        + "<p>До: системные ID и отдельные сообщения после выбора. После: имена, одна редактируемая карточка, главная сумма и явное действие. Визуальная/live-приёмка ещё предстоит.</p><h2>До</h2><p>Фрагменты настоящих шаблонов fc9ac54, синтетические значения. Чек сокращён после итоговых долей.</p></header><main>"
        + before
        + "</main><header><h2>После · настоящие экраны ветки #84</h2></header><main>"
        + "\n".join(cards)
        + "</main><footer>Воспроизведение: <code>uv run python -m scripts.render_ux84</code>. Никаких внешних запросов, токенов владельца или production.</footer></html>"
    )
    print("Rendered", len(cards), "actual template examples:", output)


if __name__ == "__main__":
    asyncio.run(render())
