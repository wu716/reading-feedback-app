"""Validated calendar and deliverable contracts shared by planning and feedback."""
from datetime import date, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeedbackRule(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    frequency: Literal["none", "daily", "weekly", "dates"] = "none"
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    dates: list[date] = Field(default_factory=list, max_length=732)
    add_dates: list[date] = Field(default_factory=list, max_length=732)
    skip_dates: list[date] = Field(default_factory=list, max_length=732)
    deadline: str = Field(default="21:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    remind_at: str = Field(default="20:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    reminders: bool = False
    deliverable: str = Field(default="", max_length=4000)
    formats: list[Literal["text", "link", "image", "document", "audio", "video", "other"]] = Field(default_factory=list, max_length=7)
    criteria: str = Field(default="", max_length=4000)
    min_words: int | None = Field(default=None, ge=1, le=1000000)

    @model_validator(mode="after")
    def validate_rule(self):
        if any(d not in range(7) for d in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays):
            raise ValueError("请选择有效且不重复的星期")
        if self.frequency == "weekly" and not self.weekdays:
            raise ValueError("请选择反馈星期")
        if self.frequency != "none" and not self.deliverable:
            raise ValueError("请说明每次要交付什么")
        if self.remind_at > self.deadline:
            raise ValueError("提醒时间应不晚于当日截止时间")
        return self

    def materialize(self, start, end):
        if any(d < start or d > end for d in self.dates + self.add_dates + self.skip_dates):
            raise ValueError("反馈日期应在本轮开始与结束日期之间")
        if self.frequency == "none":
            return []
        days, current = set(self.dates if self.frequency == "dates" else []), start
        while current <= end:
            if self.frequency == "daily" or self.frequency == "weekly" and current.weekday() in self.weekdays:
                days.add(current)
            current += timedelta(days=1)
        days.update(self.add_dates)
        days.difference_update(self.skip_dates)
        if not days:
            raise ValueError("请选择实际反馈日期，或暂不设置反馈节点")
        return sorted(days)
