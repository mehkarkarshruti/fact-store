import os
import sys
import json
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from google import genai

load_dotenv()
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY is missing")

client = genai.Client(api_key=api_key)
MODEL = "gemini-3.6-flash"


class DocumentFactPoint(BaseModel):
    source_doc: str = Field(description="Filename of the source document.")
    page_num: int = Field(description="Exact page number.")
    value: str = Field(description="Extracted value and unit.")
    time_period: Optional[str] = Field(None, description="Time period represented.")
    evidence_text: str = Field(description="Verbatim supporting quote from document.")


class MultiDocReconciliation(BaseModel):
    metric_name: str = Field(description="Unified metric or operational dimension (e.g., Revenue, Pincode Reach, Net Loss).")
    status: str = Field(
        description="One of: 'CONSISTENT_TIMELINE', 'CORROBORATED', 'CONTRADICTION', 'UNRECONCILED'"
    )
    synthesis: str = Field(
        description="Multi-document synthesis explaining the trajectory, alignment, or conflicts across all sources."
    )
    data_points: list[DocumentFactPoint] = Field(
        description="Evidence points collected across all documents mentioning this metric."
    )


class MultiDocReport(BaseModel):
    reconciliations: list[MultiDocReconciliation]


def load_facts_from_files(file_paths: list[str]) -> list[dict]:
    all_facts = []
    for path in file_paths:
        doc_name = os.path.basename(path).replace("_facts.json", "")
        with open(path, "r", encoding="utf-8") as f:
            facts = json.load(f)
            for fact in facts:
                fact["origin_file"] = doc_name
                all_facts.append(fact)
    return all_facts


def run_multi_document_reconciliation(
    facts_files: list[str], max_metrics: int = 10
) -> list[MultiDocReconciliation]:
    all_facts = load_facts_from_files(facts_files)

    prompt = f"""You are an expert multi-document corporate filing auditor and reconciliation engine.

Analyze this unified pool of extracted facts gathered across multiple corporate filings ({len(facts_files)} documents):
{json.dumps(all_facts, indent=2)}

TASK:
1. Identify up to {max_metrics} key operational or financial metrics tracked across these documents (e.g., Revenue, Pincodes, Parcel Volume, Net Profit/Loss, Market Share).
2. For each metric, link every data point across all documents where it appears.
3. Classify the status:
   - "CORROBORATED": Two or more documents state the exact same figure for the same period.
   - "CONSISTENT_TIMELINE": The metric evolves logically across time periods (e.g., FY22 IPO baseline -> FY24 actuals).
   - "CONTRADICTION": Conflicting values for identical time periods that cannot be reconciled.
   - "UNRECONCILED": Discrepancies due to shifting accounting bases or unclear scopes.
4. Enforce strict verbatim quotes and page numbers for every data point.
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": MultiDocReport,
            "temperature": 0.1,
        },
    )

    try:
        report: MultiDocReport = response.parsed
        return report.reconciliations
    except Exception:
        data = json.loads(response.text)
        return [MultiDocReconciliation(**item) for item in data.get("reconciliations", [])]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python compare.py <file1.json> <file2.json> [file3.json ...] [output.json]")
        sys.exit(1)

    args = sys.argv[1:]
    if args[-1].endswith(".json") and not args[-1].endswith("_facts.json"):
        out_file = args[-1]
        input_files = args[:-1]
    else:
        out_file = "../db/delhivery/corpus_reconciliation.json"
        input_files = args

    print(f"Reconciling facts across {len(input_files)} document stores...")
    results = run_multi_document_reconciliation(input_files)

    Path(out_file).parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump([r.model_dump() for r in results], f, indent=2)

    print(f"Reconciliation complete! Generated {len(results)} multi-document metric tracks saved to {out_file}")