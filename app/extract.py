import os
import sys
import json
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError

from schema import Fact, FactList
from prompts import EXTRACT_PROMPT
from pdf_reader import load_pages, chunk_pages, format_chunk_for_prompt

# Load environment variables
load_dotenv()
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

api_key = os.environ.get("GEMINI_API_KEY")

if not api_key:
    raise ValueError("GEMINI_API_KEY is missing")

client = genai.Client(api_key=api_key)
MODEL = "gemini-3.6-flash"


def extract_facts_from_chunk(chunk: list[dict], max_retries: int = 3) -> list[Fact]:
    """Formats chunk with page numbers and calls Gemini with automatic rate-limit and 503 backoff."""
    chunk_text = format_chunk_for_prompt(chunk)
    prompt = EXTRACT_PROMPT.format(chunk=chunk_text)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": FactList,
                    "temperature": 0.1,
                },
            )
            try:
                parsed: FactList = response.parsed
                return parsed.facts
            except Exception:
                data = json.loads(response.text)
                return [Fact(**f) for f in data.get("facts", [])]

        except APIError as e:
            err_msg = str(e).lower()
            if "429" in err_msg or "503" in err_msg or "quota" in err_msg or "unavailable" in err_msg:
                wait_time = (attempt + 1) * 10
                err_code = getattr(e, "code", "Transient")
                print(f"  [Server busy / Rate limit ({err_code})] Retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"  [Unrecoverable API Error]: {e}")
                raise e
        except Exception as e:
            print(f"  [Unexpected Error]: {e}")
            break

    return []


def extract_facts_from_pdf(
    pdf_path: str, 
    pages_per_chunk: int = 3, 
    sleep_sec: float = 6.0,
    max_chunks: int = None
) -> list[Fact]:
    """Reads PDF, chunks it, and extracts verifiable facts."""
    doc_name = os.path.basename(pdf_path)
    pages = load_pages(pdf_path)
    chunks = chunk_pages(pages, pages_per_chunk=pages_per_chunk)

    if max_chunks:
        chunks = chunks[:max_chunks]

    all_facts: list[Fact] = []
    print(f"[{doc_name}] Loaded {len(pages)} pages. Processing {len(chunks)} chunks...")

    for idx, chunk in enumerate(chunks):
        start_p = chunk[0]["page_number"]
        end_p = chunk[-1]["page_number"]
        print(f"[{doc_name}] Chunk {idx + 1}/{len(chunks)} (Pages {start_p}-{end_p})...")

        facts = extract_facts_from_chunk(chunk)
        for f_idx, f in enumerate(facts, 1):
            f.fact_id = f"c{idx + 1}_f{f_idx}"
            f.source_doc = doc_name
            if f.page_num is None:
                f.page_num = start_p

        all_facts.extend(facts)
        print(f"  -> Extracted {len(facts)} facts so far.")

        # Respect free-tier rate limits
        time.sleep(sleep_sec)

    return all_facts


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python extract.py <path_to_pdf> [output_json_path] [max_chunks]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "facts_output.json"
    max_c = int(sys.argv[3]) if len(sys.argv) > 3 else None

    facts = extract_facts_from_pdf(pdf_path, max_chunks=max_c)

    # Ensure output directory exists
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([fact.model_dump() for fact in facts], f, indent=2)

    print(f"\nCompleted! Saved {len(facts)} facts to {out_path}")