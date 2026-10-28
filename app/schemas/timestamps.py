"""UTC wire timestamps; timezone-less values cannot identify an instant."""

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, Field


def _as_utc(value: datetime) -> datetime:
    # AwareDatetime validates awareness before this conversion. Pydantic emits UTC as Z.
    return value.astimezone(UTC)


UTCDateTime = Annotated[
    AwareDatetime,
    AfterValidator(_as_utc),
    Field(description="Timezone-aware ISO 8601 timestamp in UTC with suffix Z"),
]
