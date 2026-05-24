from typing import Any

from pydantic import BaseModel, Field


class FilterParams(BaseModel):
    start: int | None = Field(default=None, description="Start year")
    end: int | None = Field(default=None, description="End year")
    region: str | None = Field(default=None, description="State or region filter")
    program: str | None = Field(default=None, description="Program filter")


class CountResponse(BaseModel):
    count: int


class KPIBundle(BaseModel):
    metrics: dict[str, Any]


class ChartPoint(BaseModel):
    label: str
    value: float


class SeriesBundle(BaseModel):
    title: str
    data: list[ChartPoint]


class OptionsResponse(BaseModel):
    years: list[int] = []
    regions: list[str] = []
    programs: list[str] = []


class ApiMessage(BaseModel):
    message: str
    details: dict[str, Any] | None = None
