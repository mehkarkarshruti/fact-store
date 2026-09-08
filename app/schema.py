from pydantic import BaseModel, Field
from typing import Optional
import uuid


class Fact(BaseModel):
    fact_id: str = Field(
        default_factory=lambda: f"fact_{uuid.uuid4().hex[:8]}",
        description="Unique identifier for tracking and pairing facts."
    )
    subject: str = Field(
        description="Entity or primary topic (e.g. 'Delhivery revenue', 'Pincodes covered', 'India real GDP')."
    )
    predicate: str = Field(
        description="Action, relation, or state (e.g. 'reported', 'expanded to', 'stood at')."
    )
    value: str = Field(
        description="Numerical metric or qualitative state (e.g. '7241', '18500', 'Active')."
    )
    unit: Optional[str] = Field(
        default=None,
        description="Unit of measurement if applicable (e.g. 'INR Crore', '%', 'million')."
    )
    time_period: Optional[str] = Field(
        default=None,
        description="Fiscal period or temporal boundary (e.g. 'FY22', 'FY24', 'Q4 FY24', 'As of Dec 2021')."
    )
    evidence_text: str = Field(
        description="Exact verbatim sentence or table line from the source document supporting this fact."
    )
    source_doc: Optional[str] = Field(
        default=None,
        description="Filename of the source PDF (injected automatically during ingestion)."
    )
    page_num: Optional[int] = Field(
        default=None,
        description="1-indexed page number in the source PDF where evidence was found."
    )


class FactList(BaseModel):
    facts: list[Fact]