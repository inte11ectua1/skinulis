"""No-VPS laptop deployment must remain opt-in and never expose the database."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_laptop_compose_is_separate_and_bot_opt_in() -> None:
    base = (ROOT / "compose.yaml").read_text()
    laptop = (ROOT / "compose.laptop.yaml").read_text()

    assert "  bot:" not in base
    assert "  bot:" in laptop
    assert "profiles: [polling]" in laptop
    assert 'command: ["python", "-m", "bot.main"]' in laptop
    assert "container_name:" in laptop
    assert "API_BASE_URL: http://api:8000" in laptop
    assert 'TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}' in laptop
    assert "depends_on:" in laptop and "condition: service_healthy" in laptop


def test_laptop_compose_keeps_db_and_api_private() -> None:
    base = (ROOT / "compose.yaml").read_text()
    laptop = (ROOT / "compose.laptop.yaml").read_text()

    assert '127.0.0.1:${API_PORT:-8000}:8000' in laptop
    assert "    networks: [database]" in laptop
    assert "    networks: [application, database]" in laptop
    assert "    networks: [application, telegram]" in laptop
    assert "  application:\n    internal: true" in laptop
    assert "  database:\n    internal: true" in laptop
    assert "  telegram: {}" in laptop
    assert "    ports:" not in base.split("  db:", 1)[1].split("\n  migrate:", 1)[0]
    assert "    ports:" not in laptop.split("  bot:", 1)[1].split("\nnetworks:", 1)[0]
    assert "JWT_SECRET_KEY" not in laptop.split("  bot:", 1)[1]
    assert "POSTGRES_PASSWORD" not in laptop.split("  bot:", 1)[1]


def test_laptop_docs_require_non_destructive_and_no_claim_of_original_g5() -> None:
    instructions = (ROOT / "docs/operations/LAPTOP_HOSTING.md").read_text()
    adr = (ROOT / "docs/adr/003-laptop-as-demo-host.md").read_text()
    assert "down -v" in instructions and "**Нельзя:**" in instructions
    assert "APP_COMMIT_SHA" in instructions and "/health" in instructions
    assert "не**" not in instructions
    assert "не** публичный HTTPS" in instructions
    assert "не** доказывают" in adr or "**не** доказывают" in adr
