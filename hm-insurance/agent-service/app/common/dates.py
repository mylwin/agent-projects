from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, PlainSerializer

BUSINESS_TIME_ZONE = ZoneInfo("Asia/Shanghai")
BusinessDateTime = Annotated[
    AwareDatetime,
    PlainSerializer(
        lambda value: value.astimezone(BUSINESS_TIME_ZONE),
        return_type=datetime,
        when_used="json",
    ),
]
