from typing import Annotated, Literal

from pydantic import Field, model_validator

from app.schemas.analytics import Calculation, Chart, Filter, Metric, StrictModel, TopTable
from app.schemas.workspace import ReportTitle

Title = Annotated[str, Field(min_length=1, max_length=120)]


class MetricBlock(Metric):
    title: Title = "Metric"


class ChartBlock(Chart):
    title: Title = "Chart"


class TableBlock(TopTable):
    title: Title = "Table"


class NoteBlock(Calculation):
    type: Literal["note"]
    title: Title = "Note"
    text: str = Field(default="", max_length=10000)


ReportBlock = Annotated[MetricBlock | ChartBlock | TableBlock | NoteBlock, Field(discriminator="type")]


class ReportDefinition(StrictModel):
    version: Literal[1] = 1
    blocks: list[ReportBlock] = Field(default_factory=list, max_length=20)
    filters: list[Filter] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [block.id for block in self.blocks]
        if len(ids) != len(set(ids)):
            raise ValueError("Report block IDs must be unique, including notes.")
        return self


class ReportVersion(StrictModel):
    expected_revision: int = Field(ge=1, strict=True)
    expected_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SaveReport(ReportVersion, ReportTitle):
    definition: ReportDefinition
