"""Every HTTP operation must remain explainable from its generated OpenAPI."""

import secrets
from typing import Any

from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


def test_all_operations_document_request_and_success_examples() -> None:
    settings = Settings(
        _env_file=None, postgres_password=SecretStr(secrets.token_urlsafe(32))
    )
    schema = create_app(settings).openapi()

    def has_example(value: Any, seen: frozenset[str] = frozenset()) -> bool:
        if isinstance(value, dict):
            if "example" in value or value.get("examples"):
                return True
            reference = value.get("$ref")
            if reference and reference not in seen:
                target: Any = schema
                for key in reference.removeprefix("#/").split("/"):
                    target = target[key]
                if has_example(target, seen | {reference}):
                    return True
            return any(
                has_example(child, seen)
                for key, child in value.items()
                if key != "$ref"
            )
        return isinstance(value, list) and any(
            has_example(child, seen) for child in value
        )

    missing: list[str] = []
    for path, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "put", "delete", "patch"}:
                continue
            assert operation["summary"]
            if "requestBody" in operation and not has_example(operation["requestBody"]):
                missing.append(f"{method.upper()} {path}: request")
            if not any(
                has_example(response)
                for code, response in operation["responses"].items()
                if code.startswith("2")
            ):
                missing.append(f"{method.upper()} {path}: response")
    assert not missing, "\n".join(missing)


def test_documented_expense_examples_preserve_exact_wire_values() -> None:
    from app.schemas.expenses import (
        ExpenseProfile,
        PreviewProfile,
        ReceiptExpenseProfile,
        ReceiptPreviewProfile,
    )

    for dto in (
        PreviewProfile,
        ReceiptPreviewProfile,
        ExpenseProfile,
        ReceiptExpenseProfile,
    ):
        for example in dto.model_json_schema()["examples"]:
            result = dto.model_validate(example).model_dump(mode="json")
            assert result == example
            assert (
                sum(int(s["amount"].replace(".", "")) for s in result["shares"])
                == 10000
            )
