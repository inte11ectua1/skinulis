"""Temporary T-04 negative probe; removed after verifying the required check."""


def test_required_ci_rejects_failure() -> None:
    raise AssertionError("Intentional T-04 probe: required tests must block merge")
