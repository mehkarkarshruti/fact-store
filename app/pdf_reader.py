import pymupdf


def load_pages(pdf_path: str) -> list[dict]:
    """
    Reads any PDF file dynamically page by page.
    Returns a list of dicts with 1-indexed page numbers and extracted raw text.
    """
    doc = pymupdf.open(pdf_path)
    pages = []
    for page_num in range(len(doc)):
        text = doc[page_num].get_text("text").strip()
        if text:
            pages.append({
                "page_number": page_num + 1,
                "text": text
            })
    doc.close()
    return pages


def chunk_pages(pages: list[dict], pages_per_chunk: int = 3) -> list[list[dict]]:
    """
    Groups pages into manageable chunks (default 3 pages)
    to balance extraction depth with API token safety.
    """
    chunks = []
    for i in range(0, len(pages), pages_per_chunk):
        chunks.append(pages[i : i + pages_per_chunk])
    return chunks


def format_chunk_for_prompt(chunk: list[dict]) -> str:
    """
    Tags page boundaries clearly with headers so the LLM has exact
    page coordinates to ground its evidence citations.
    """
    parts = []
    for p in chunk:
        parts.append(f"--- PAGE {p['page_number']} ---\n{p['text']}")
    return "\n\n".join(parts)