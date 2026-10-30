from copy import deepcopy
from random import Random

import pytest

from app.services.expenses import ExpenseSnapshotInvalid
from app.services.settlement_plan import Transfer, greedy_plan


@pytest.mark.parametrize(
    "vector,expected",
    [
        ({}, ()),
        ({1: 0}, ()),
        (
            {10: 800, 20: 700, 30: -700, 40: -500, 50: -300},
            (
                Transfer(30, 10, 700),
                Transfer(40, 10, 100),
                Transfer(40, 20, 400),
                Transfer(50, 20, 300),
            ),
        ),
        ({1: 10, 2: 10, 4: -10, 3: -10}, (Transfer(3, 1, 10), Transfer(4, 2, 10))),
        ({1: 10**40, 2: -(10**40)}, (Transfer(2, 1, 10**40),)),
    ],
)
def test_greedy(vector: dict[int, int], expected: tuple[Transfer, ...]) -> None:
    original = deepcopy(vector)
    assert (
        greedy_plan(vector)
        == expected
        == greedy_plan(dict(reversed(list(vector.items()))))
    )
    assert vector == original


@pytest.mark.parametrize(
    "vector", [{1: 1}, {True: 0}, {0: 0}, {2**63: 0}, {1: True}, {1: 1.0}, {"1": 0}]
)
def test_invalid(vector: dict[int, int]) -> None:
    with pytest.raises(ExpenseSnapshotInvalid):
        greedy_plan(vector)


def test_generated_vectors_conserve_every_kopeck() -> None:
    random = Random(46)
    for _ in range(100):
        vector = {i: random.randrange(-(10**25), 10**25) for i in range(1, 30)}
        vector[30] = -sum(vector.values())
        remaining = vector.copy()
        for t in greedy_plan(vector):
            assert (
                t.amount_kopecks > 0 and vector[t.sender_id] < 0 < vector[t.receiver_id]
            )
            remaining[t.sender_id] += t.amount_kopecks
            remaining[t.receiver_id] -= t.amount_kopecks
        assert set(remaining.values()) == {0}


def test_typed_fixtures_and_four_documented_routes() -> None:
    import json
    from pathlib import Path

    from fastapi import FastAPI

    from app.api.balances import build_router
    from app.schemas.balances import BalancesResponse, PlanResponse

    data = json.loads(
        Path("docs/finance/fixtures/O-06_BALANCES.json").read_text(encoding="utf-8")
    )
    assert (
        BalancesResponse.model_validate(data["balances"]).model_dump()
        == data["balances"]
    )
    assert PlanResponse.model_validate(data["plan"]).model_dump() == data["plan"]
    app = FastAPI()
    app.include_router(build_router())
    app.include_router(build_router(internal=True))
    schema = app.openapi()
    assert len(schema["paths"]) == 4
    assert all(set(path) == {"get"} for path in schema["paths"].values())
