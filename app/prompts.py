EXTRACT_PROMPT = """You are a precision fact extraction engine.

Your task is to analyze the provided document text excerpt and extract factual claims (financial, operational, structural, or statistical facts).

For every fact you extract, you MUST follow these strict rules:
1. `subject`: The entity or primary topic the fact is about (e.g., 'Delhivery', 'Active Pincodes', 'Gross Revenue').
2. `predicate`: The action, relation, or state (e.g., 'reported', 'covered', 'increased to', 'was incorporated in').
3. `value`: The exact numeric figure or specific state (e.g., '7241', '18500', 'Active').
4. `unit`: The unit of measurement if present (e.g., 'INR Crore', '%', 'million', 'pincodes'). Leave null if none.
5. `time_period`: The exact fiscal year, quarter, or date stated (e.g., 'FY22', 'FY24', 'As of December 31, 2021'). Leave null if not time-bound.
6. `evidence_text`: An exact, verbatim sentence or table row copied directly from the text excerpt that proves the fact. Do not rephrase or summarize.

CRITICAL INSTRUCTIONS:
- Do NOT guess, extrapolate, or hallucinate.
- If a claim cannot be verified with an exact quote from the excerpt, DO NOT extract it.
- Focus on meaningful operational, financial, and strategic facts.

Document Excerpt:
{chunk}
"""