"""The same contract will be used by the report editor and snapshot service."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ColumnKey = Annotated[str, Field(pattern=r"^c[0-9]{1,3}$")]
Label = Annotated[str, Field(max_length=512)]
DecimalText = Annotated[str, Field(min_length=1, max_length=100)]
Operation = Literal["sum", "average", "count", "min", "max"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CategoryFilter(StrictModel):
    type: Literal["category"]
    column: ColumnKey
    values: list[Label] = Field(min_length=1, max_length=50)


class DateFilter(StrictModel):
    type: Literal["date_range"]
    column: ColumnKey
    start: date
    end: date

    @model_validator(mode="after")
    def ordered(self):
        if self.start > self.end or self.end == date.max:
            raise ValueError("Choose start <= end, with end before 9999-12-31.")
        return self


class NumberFilter(StrictModel):
    type: Literal["number_range"]
    column: ColumnKey
    minimum: DecimalText | None = None
    maximum: DecimalText | None = None

    @model_validator(mode="after")
    def bounded(self):
        if self.minimum is None and self.maximum is None:
            raise ValueError("Supply a minimum or maximum.")
        return self


class MissingFilter(StrictModel):
    type: Literal["missing"]
    column: ColumnKey
    missing: bool = True


Filter = Annotated[CategoryFilter | DateFilter | NumberFilter | MissingFilter, Field(discriminator="type")]


class Calculation(StrictModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class Metric(Calculation):
    type: Literal["metric"]
    operation: Operation
    # No column means COUNT(*), and is only valid for count.
    column: ColumnKey | None = None
    group_by: ColumnKey | None = None

    @model_validator(mode="after")
    def needs_column(self):
        if self.operation != "count" and self.column is None:
            raise ValueError("This operation needs a column.")
        return self


class Chart(Calculation):
    type: Literal["chart"]
    chart_type: Literal["bar", "line"]
    operation: Operation
    column: ColumnKey | None = None
    group_by: ColumnKey

    @model_validator(mode="after")
    def needs_column(self):
        if self.operation != "count" and self.column is None:
            raise ValueError("This operation needs a column.")
        return self


class TopTable(Calculation):
    type: Literal["table"]
    sort_by: ColumnKey
    direction: Literal["asc", "desc"] = "desc"
    limit: int = Field(default=10, ge=1, le=100)


Block = Annotated[Metric | Chart | TopTable, Field(discriminator="type")]


class EvaluateRequest(StrictModel):
    expected_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    filters: list[Filter] = Field(default_factory=list, max_length=10)
    calculations: list[Block] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [block.id for block in self.calculations]
        if len(ids) != len(set(ids)):
            raise ValueError("Calculation IDs must be unique.")
        return self
