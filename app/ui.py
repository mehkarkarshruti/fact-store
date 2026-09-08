"""FactStore Audit Engine — Streamlit UI.

Run from the project root with:
    streamlit run app/ui.py
"""

from __future__ import annotations

import html
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import streamlit as st

# Inject app directory and project root to avoid import issues
APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from compare import run_multi_document_reconciliation
from extract import extract_facts_from_pdf

DATA_DIR = ROOT_DIR / "data" / "uploads"
DB_DIR = ROOT_DIR / "db"
# Raw per-document extracted facts (pre-comparison) live separately from
# actual cross-document reconciliation output, so the Audit Findings view
# can never accidentally treat a raw fact file as a "finding".
FACTS_DIR = DB_DIR / "facts" / "uploads"
RECON_DIR = DB_DIR / "reconciliations" / "uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
FACTS_DIR.mkdir(parents=True, exist_ok=True)
RECON_DIR.mkdir(parents=True, exist_ok=True)

st.set_page_config(
    page_title="FactStore | Audit workspace",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# Live Terminal Log Streamer
# -----------------------------------------------------------------------------
class TerminalLogStreamer:
    """Redirects stdout print statements directly into an on-screen console."""
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.logs: list[str] = []
        self.stdout = sys.stdout

    def write(self, message: str):
        self.stdout.write(message)
        clean = message.strip()
        if clean:
            self.logs.append(clean)
            tail = "\n".join(self.logs[-22:])
            self.placeholder.code(tail, language="bash")

    def flush(self):
        self.stdout.flush()

# -----------------------------------------------------------------------------
# Theme and Styling
# -----------------------------------------------------------------------------
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

is_dark = st.session_state.theme == "dark"

COLORS = {
    "bg": "#0a0c10" if is_dark else "#f8fafc",
    "surface": "#12171f" if is_dark else "#ffffff",
    "surface_alt": "#1a212d" if is_dark else "#f1f5f9",
    "border": "#283344" if is_dark else "#cbd5e1",
    "text": "#f0f6fc" if is_dark else "#0f172a",
    "muted": "#8b949e" if is_dark else "#64748b",
    "accent": "#d97706" if is_dark else "#b45309",
    "accent_soft": "#2d2013" if is_dark else "#fef3c7",
    "green": "#3fb950" if is_dark else "#16a34a",
    "green_bg": "#122619" if is_dark else "#dcfce7",
    "blue": "#58a6ff" if is_dark else "#0284c7",
    "blue_bg": "#13233a" if is_dark else "#e0f2fe",
    "red": "#f85149" if is_dark else "#dc2626",
    "red_bg": "#34171a" if is_dark else "#fee2e2",
    "yellow": "#d29922" if is_dark else "#ca8a04",
    "yellow_bg": "#33250e" if is_dark else "#fef9c3",
}

st.markdown(
    f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&display=swap');
        
        :root {{ color-scheme: {'dark' if is_dark else 'light'}; }}
        html, body, [class*="css"] {{ font-family: 'DM Sans', sans-serif; }}
        
        .stApp {{ 
            background-color: {COLORS['bg']} !important; 
            color: {COLORS['text']} !important; 
        }}
        .stApp * {{ color: {COLORS['text']}; }}
        
        header, header [data-testid="stHeader"] {{ 
            background: {COLORS['bg']} !important; 
            color: {COLORS['text']} !important;
        }}
        footer {{ visibility: hidden; }}
        
        .block-container {{ max-width: 1450px; padding: 2rem 2.5rem 3rem; }}
        [data-testid="stSidebar"] {{ 
            background-color: {COLORS['surface']} !important; 
            border-right: 1px solid {COLORS['border']} !important; 
        }}

        /* Clean Streamlit Layout Artifacts & Prevent Phantom Boxes */
        div[data-testid="stWidgetLabel"]:has(span:empty),
        div[data-testid="stWidgetLabel"][aria-hidden="true"] {{
            display: none !important;
            margin: 0 !important;
            padding: 0 !important;
            height: 0 !important;
        }}
        div[data-testid="element-container"]:has(> div:empty) {{
            display: none !important;
        }}
        /* Collapse any empty markdown wrapper Streamlit leaves behind */
        div[data-testid="stMarkdownContainer"]:empty,
        div[data-testid="element-container"]:has(> div[data-testid="stMarkdownContainer"]:empty) {{
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
        }}

        /* Header Brand */
        .brand {{ display:flex; align-items:center; gap:.7rem; margin-bottom:2rem; }}
        .brand-mark {{ width:34px; height:34px; display:grid; place-items:center; border-radius:8px; background:{COLORS['accent']}; color:white !important; font-size:1.15rem; font-weight:700; }}
        .brand-name {{ color:{COLORS['text']} !important; font-weight:700; font-size:1.05rem; letter-spacing:-.02em; }}
        .brand-sub {{ color:{COLORS['muted']} !important; font: .65rem 'DM Mono', monospace; letter-spacing:.08em; text-transform:uppercase; margin-top:2px; }}
        
        .eyebrow {{ color:{COLORS['accent']} !important; font:600 .72rem 'DM Mono', monospace; text-transform:uppercase; letter-spacing:.08em; margin-bottom:.4rem; }}
        .hero-title {{ color:{COLORS['text']} !important; font-size:1.85rem; font-weight:700; letter-spacing:-.03em; margin:0; }}
        .hero-copy {{ color:{COLORS['muted']} !important; font-size:.92rem; line-height:1.55; max-width:700px; margin:.5rem 0 1.2rem; }}
        .section-label {{ color:{COLORS['muted']} !important; font:600 .72rem 'DM Mono', monospace; text-transform:uppercase; letter-spacing:.09em; margin:1.2rem 0 .5rem; }}
        
        /* Cards */
        .metric-card {{ background:{COLORS['surface']} !important; border:1px solid {COLORS['border']} !important; border-radius:10px; padding:.9rem 1.1rem; }}
        .metric-label {{ color:{COLORS['muted']} !important; font-size:.75rem; }}
        .metric-value {{ color:{COLORS['text']} !important; font-size:1.45rem; font-weight:700; margin-top:.25rem; font-family: 'DM Mono', monospace; }}
        .metric-note {{ color:{COLORS['muted']} !important; font-size:.7rem; margin-top:.15rem; }}
        
        .detail-card {{ background:{COLORS['surface']} !important; border:1px solid {COLORS['border']} !important; border-radius:12px; padding:1.4rem; }}
        .detail-title {{ color:{COLORS['text']} !important; font-size:1.3rem; font-weight:700; margin:0; }}
        .synthesis {{ color:{COLORS['text']} !important; font-size:.95rem; line-height:1.6; margin:1rem 0; }}
        
        .evidence {{ background:{COLORS['surface_alt']} !important; border:1px solid {COLORS['border']} !important; border-radius:8px; padding:.9rem 1rem; margin:.6rem 0; }}
        .evidence-meta {{ color:{COLORS['muted']} !important; font: .72rem 'DM Mono', monospace; }}
        .evidence-value {{ color:{COLORS['accent']} !important; font-size:1.05rem; font-weight:700; margin:.35rem 0; }}
        .quote {{ color:{COLORS['text']} !important; border-left:3px solid {COLORS['accent']}; padding-left:.8rem; font:italic .9rem/1.5 Georgia, serif; }}
        
        /* Status Badges */
        .status {{ display:inline-flex; align-items:center; border-radius:6px; padding:.25rem .55rem; font:600 .68rem 'DM Mono', monospace; }}
        .status-green {{ color:{COLORS['green']} !important; background:{COLORS['green_bg']} !important; border:1px solid {COLORS['green']}; }}
        .status-blue {{ color:{COLORS['blue']} !important; background:{COLORS['blue_bg']} !important; border:1px solid {COLORS['blue']}; }}
        .status-red {{ color:{COLORS['red']} !important; background:{COLORS['red_bg']} !important; border:1px solid {COLORS['red']}; }}
        .status-yellow {{ color:{COLORS['yellow']} !important; background:{COLORS['yellow_bg']} !important; border:1px solid {COLORS['yellow']}; }}
        
        .case-card {{ border:1px solid {COLORS['border']} !important; border-radius:12px; padding:1rem; background:{COLORS['surface']} !important; }}
        .case-card strong {{ display:block; color:{COLORS['text']} !important; font-size:.9rem; margin:.45rem 0; }}
        .case-card span {{ color:{COLORS['muted']} !important; font-size:.78rem; line-height:1.45; }}
        .case-card small {{ display:block; color:{COLORS['muted']} !important; font: .65rem 'DM Mono', monospace; margin-top:.85rem; }}
        .case-eyebrow {{ font:600 .65rem 'DM Mono', monospace; text-transform:uppercase; letter-spacing:.08em; }}
        .case-green {{ border-top:3px solid {COLORS['green']} !important; }} .case-green .case-eyebrow {{ color:{COLORS['green']} !important; }}
        .case-red {{ border-top:3px solid {COLORS['red']} !important; }} .case-red .case-eyebrow {{ color:{COLORS['red']} !important; }}
        .case-blue {{ border-top:3px solid {COLORS['blue']} !important; }} .case-blue .case-eyebrow {{ color:{COLORS['blue']} !important; }}
        .case-yellow {{ border-top:3px solid {COLORS['yellow']} !important; }} .case-yellow .case-eyebrow {{ color:{COLORS['yellow']} !important; }}

        /* File Uploader and Drag-and-Drop Area */
        [data-testid="stFileUploader"] {{ background-color: transparent !important; }}
        [data-testid="stFileUploaderDropzone"] {{
            background-color: {COLORS['surface']} !important;
            border: 2px dashed {COLORS['border']} !important;
            border-radius: 10px !important;
        }}
        [data-testid="stFileUploaderDropzone"] * {{ color: {COLORS['text']} !important; }}
        [data-testid="stFileUploaderDropzone"] small {{ color: {COLORS['muted']} !important; }}
        /* FIX (dark-mode glitch, part 2): the "Browse files" button is a native
           Streamlit button that follows Streamlit's OWN internal theme (often
           tied to the browser/OS dark-mode preference), independent of our
           custom is_dark toggle. Our global ".stApp * {{ color }}" rule was
           forcing dark text onto that button while its background stayed on
           Streamlit's native (sometimes dark) theme — dark text on a dark
           background reads as a solid black box. Pin both explicitly here. */
        [data-testid="stFileUploaderDropzone"] button {{
            background-color: {COLORS['surface']} !important;
            background: {COLORS['surface']} !important;
            border: 1px solid {COLORS['border']} !important;
            color: {COLORS['text']} !important;
        }}
        [data-testid="stFileUploaderDropzone"] button span,
        [data-testid="stFileUploaderDropzone"] button p,
        [data-testid="stFileUploaderDropzone"] button div {{
            background: transparent !important;
            color: {COLORS['text']} !important;
        }}
        [data-testid="stFileUploaderDropzone"] [data-testid="stBaseButton-secondary"] {{
            background-color: {COLORS['surface']} !important;
            background: {COLORS['surface']} !important;
            border: 1px solid {COLORS['border']} !important;
            color: {COLORS['text']} !important;
        }}
        [data-testid="stFileUploaderDropzone"] button:hover {{
            border-color: {COLORS['accent']} !important;
        }}
        [data-testid="stFileUploaderFile"] {{
            background-color: {COLORS['surface_alt']} !important;
            border: 1px solid {COLORS['border']} !important;
            border-radius: 6px !important;
        }}
        [data-testid="stFileUploaderFile"] * {{ color: {COLORS['text']} !important; }}

        /* Expander Contrast */
        [data-testid="stExpander"] {{
            background-color: {COLORS['surface']} !important;
            border: 1px solid {COLORS['border']} !important;
            border-radius: 10px !important;
        }}
        [data-testid="stExpander"] summary {{
            background-color: {COLORS['surface']} !important;
            color: {COLORS['text']} !important;
        }}
        [data-testid="stExpander"] summary * {{ color: {COLORS['text']} !important; }}
        [data-testid="stExpanderDetails"] {{
            background-color: {COLORS['surface']} !important;
            border-top: 1px solid {COLORS['border']} !important;
        }}

        /* Buttons */
        div[data-testid="stButton"] > button {{ 
            border-radius:8px; 
            border:1px solid {COLORS['border']} !important; 
            min-height:2.35rem; 
            font-size:.82rem; 
            background:{COLORS['surface']} !important; 
            color:{COLORS['text']} !important; 
            font-weight:600;
        }}
        div[data-testid="stButton"] > button p {{ color:{COLORS['text']} !important; }}
        div[data-testid="stButton"] > button:hover {{ border-color:{COLORS['accent']} !important; }}
        
        div[data-testid="stButton"] > button[kind="primary"],
        div[data-testid="stButton"] > button[data-testid="stBaseButton-primary"] {{ 
            background:{COLORS['accent']} !important; 
            border-color:{COLORS['accent']} !important; 
            color:#ffffff !important; 
        }}
        div[data-testid="stButton"] > button[kind="primary"] * {{ color:#ffffff !important; }}
        
        /* Select and Inputs */
        .stTextInput input {{ 
            background:{COLORS['surface']} !important; 
            color:{COLORS['text']} !important; 
            caret-color:{COLORS['accent']}; 
            border:1px solid {COLORS['border']} !important; 
            border-radius: 8px !important;
        }}

        /* FIX (Bug 2): style only the OUTER select control. BaseWeb nests several
           child divs (value container / input wrapper / indicators) inside
           [data-baseweb="select"] > div — styling every one of those with its own
           background+border produced stacked/empty-looking "phantom" boxes.
           Border/background go on the outer element only; inner children are
           made transparent and borderless so only one box is ever visible. */
        [data-baseweb="select"] {{
            background:{COLORS['surface']} !important;
            border: 1px solid {COLORS['border']} !important;
            border-radius: 8px !important;
        }}
        [data-baseweb="select"] > div {{
            background: transparent !important;
            border: none !important;
            color: {COLORS['text']} !important;
        }}
        [data-baseweb="select"] span, [data-baseweb="select"] input {{ color:{COLORS['text']} !important; }}
        [data-baseweb="popover"] {{ background:{COLORS['surface']} !important; }}
        [role="option"] {{ color:{COLORS['text']} !important; background:{COLORS['surface']} !important; }}
        [role="option"]:hover {{ background:{COLORS['surface_alt']} !important; }}

        /* FIX (dark-mode glitch, part 3): Streamlit gives inline `code` spans
           (from markdown backticks, e.g. in st.caption) a FIXED dark
           background + green text by default — independent of our custom
           is_dark toggle. That's why they showed up as dark/gray pills even
           on the light theme. Override to follow our own COLORS instead. */
        code {{
            background-color: {COLORS['surface_alt']} !important;
            color: {COLORS['accent']} !important;
            border: 1px solid {COLORS['border']} !important;
            border-radius: 4px !important;
            padding: .1rem .35rem !important;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

def esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "—"))

def status_class(status: str) -> str:
    mapping = {
        "CORROBORATED": "status-green",
        "CONSISTENT_TIMELINE": "status-blue",
        "CONTRADICTION": "status-red",
        "UNRECONCILED": "status-yellow"
    }
    return mapping.get(status, "status-yellow")

def status_pill(status: str) -> str:
    label = status.replace("_", " ").title()
    return f'<span class="status {status_class(status)}">{esc(label)}</span>'

def discover_stores() -> dict[str, Path]:
    """Only surfaces actual reconciliation output. Raw per-document fact
    files (in FACTS_DIR) are intermediate data, not findings, and must
    never show up here — otherwise they render as empty "Untitled metric /
    Unreconciled" cards with 0 evidence points."""
    recon_root = DB_DIR / "reconciliations"
    if not recon_root.exists():
        return {}
    stores: dict[str, Path] = {}
    for path in sorted(recon_root.rglob("*.json")):
        label = f"{path.parent.name}/{path.name}"
        stores[label] = path
    return stores

def load_json(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []

def save_uploaded_file(uploaded_file: Any) -> Path:
    safe_name = Path(uploaded_file.name).name
    destination = DATA_DIR / safe_name
    with destination.open("wb") as buffer:
        shutil.copyfileobj(uploaded_file, buffer)
    return destination

def render_evidence_html(points: list[dict[str, Any]]) -> str:
    """Builds all evidence blocks as ONE concatenated HTML string.

    FIX (Bug 1): previously each evidence block (and the surrounding
    detail-card open/close tags) was emitted via a SEPARATE st.markdown()
    call. Streamlit wraps every markdown() call in its own container, so an
    opening '<div class="detail-card">' rendered as its own empty styled box
    (the phantom bar), and content never actually nested inside it. Building
    the full HTML as one string and calling st.markdown() exactly once fixes
    this — there is now exactly one real DOM container per card.
    """
    return "".join(
        f'<div class="evidence">'
        f'<div class="evidence-meta">{esc(point.get("source_doc"))} &nbsp;·&nbsp; '
        f'page {esc(point.get("page_num"))} &nbsp;·&nbsp; '
        f'{esc(point.get("time_period") or "Period unspecified")}</div>'
        f'<div class="evidence-value">{esc(point.get("value"))}</div>'
        f'<div class="quote">&ldquo;{esc(point.get("evidence_text"))}&rdquo;</div>'
        f'</div>'
        for point in points
    )

def render_detail_card(item: dict[str, Any]) -> str:
    """Builds a full detail-card (title + status pill + synthesis + evidence)
    as a single HTML string so it can be emitted in one st.markdown() call."""
    status = item.get("status", "UNRECONCILED")
    evidence = item.get("data_points", [])
    return (
        '<div class="detail-card">'
        '<div style="display:flex;justify-content:space-between;gap:1rem;align-items:flex-start;">'
        f'<h2 class="detail-title">{esc(item.get("metric_name", "Untitled metric"))}</h2>'
        f'{status_pill(status)}'
        '</div>'
        f'<div class="synthesis">{esc(item.get("synthesis", "No synthesis available."))}</div>'
        f'{render_evidence_html(evidence)}'
        '</div>'
    )

stores = discover_stores()
store_keys = list(stores.keys())

if "selected_store" not in st.session_state and store_keys:
    st.session_state.selected_store = store_keys[0]

# -----------------------------------------------------------------------------
# Sidebar Navigation
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(
        '<div class="brand"><div class="brand-mark">◈</div><div><div class="brand-name">FactStore</div><div class="brand-sub">Audit workspace</div></div></div>',
        unsafe_allow_html=True,
    )
    page = st.radio("Workspace", ["Overview / casebook", "Audit findings", "Ingest & reconcile"], label_visibility="collapsed")
    
    st.markdown("<div class='section-label'>Active Corpus</div>", unsafe_allow_html=True)
    if store_keys:
        current_idx = store_keys.index(st.session_state.selected_store) if st.session_state.selected_store in store_keys else 0
        st.session_state.selected_store = st.selectbox(
            "Corpus Selection",
            store_keys,
            index=current_idx,
            label_visibility="collapsed"
        )
    else:
        st.caption("No stores found.")

    st.markdown("<div class='section-label'>Appearance</div>", unsafe_allow_html=True)
    if st.button(f"Switch to {'light' if is_dark else 'dark'} mode", use_container_width=True):
        st.session_state.theme = "light" if is_dark else "dark"
        st.rerun()

    st.markdown("<div class='section-label'>About this workspace</div>", unsafe_allow_html=True)
    st.caption("Traceable facts, cross-document comparisons, and evidence-backed findings in one place.")

def casebook_item(items: list[dict[str, Any]], status: str) -> dict[str, Any] | None:
    candidates = [item for item in items if item.get("status") == status]
    return max(candidates, key=lambda item: len(item.get("data_points", [])), default=None)

def render_case(eyebrow: str, explanation: str, item: dict[str, Any] | None, tone: str) -> None:
    if item:
        body = (
            f"<strong>{esc(item.get('metric_name', 'Untitled metric'))}</strong>"
            f"<br><span>{esc(explanation)}</span>"
            f"<br><small>{len(item.get('data_points', []))} linked evidence points</small>"
        )
    else:
        body = f"<strong>Not available in this store</strong><br><span>{esc(explanation)}</span>"
    st.markdown(f'<div class="case-card case-{tone}"><div class="case-eyebrow">{esc(eyebrow)}</div>{body}</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Tab 1: Overview / Casebook
# -----------------------------------------------------------------------------
if page == "Overview / casebook":
    st.markdown('<div class="eyebrow">Fact knowledge layer / guided demo</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="hero-title">From scattered PDFs to explainable facts.</h1>', unsafe_allow_html=True)
    st.markdown('<p class="hero-copy">A friendly way to inspect what was extracted, where it came from, and why documents agree, disagree, or only appear to disagree.</p>', unsafe_allow_html=True)

    if not stores or not st.session_state.selected_store:
        st.info("No active reconciliation store loaded. Head to Ingest & reconcile to process documents.")
        st.stop()

    corpus = load_json(stores[st.session_state.selected_store])
    corroborated = casebook_item(corpus, "CORROBORATED")
    contradiction = casebook_item(corpus, "CONTRADICTION")
    contextual = casebook_item(corpus, "CONSISTENT_TIMELINE")

    st.markdown("<div class='section-label'>The cases we look for</div>", unsafe_allow_html=True)
    case_cols = st.columns(4)
    with case_cols[0]:
        render_case("01 · corroborated", "Same metric across sources, even when wording or units differ.", corroborated, "green")
    with case_cols[1]:
        render_case("02 · contradiction", "Values cannot be safely treated as the same claim.", contradiction, "red")
    with case_cols[2]:
        render_case("03 · context resolves", "Different periods, scopes, or units explain the apparent mismatch.", contextual, "blue")
    with case_cols[3]:
        render_case("04 · known limitation", "Evidence stays visible instead of pretending extraction is truth.", None, "yellow")

    st.markdown("<div class='section-label'>Featured case inspection</div>", unsafe_allow_html=True)
    featured_name = st.radio(
        "Select Case",
        ["Corroboration", "Contradiction", "Context resolves"],
        horizontal=True,
        label_visibility="collapsed"
    )
    featured = {"Corroboration": corroborated, "Contradiction": contradiction, "Context resolves": contextual}[featured_name]
    if featured:
        # FIX (Bug 1): single st.markdown() call for the entire card — see render_detail_card().
        st.markdown(render_detail_card(featured), unsafe_allow_html=True)
    else:
        st.info("This corpus does not contain the selected case.")

# -----------------------------------------------------------------------------
# Tab 2: Audit Findings
# -----------------------------------------------------------------------------
elif page == "Audit findings":
    st.markdown('<div class="eyebrow">Corpus intelligence / 01</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="hero-title">Audit findings</h1>', unsafe_allow_html=True)
    st.markdown('<p class="hero-copy">Explore reconciled metrics, inspect the source evidence behind each finding, and separate corroborated facts from unresolved discrepancies.</p>', unsafe_allow_html=True)

    if not stores or not st.session_state.selected_store:
        st.info("No reconciliation stores found. Run the ingestion pipeline to begin.")
        st.stop()

    reconciliations = load_json(stores[st.session_state.selected_store])
    statuses = sorted({item.get("status", "UNRECONCILED") for item in reconciliations})
    total_evidence = sum(len(item.get("data_points", [])) for item in reconciliations)
    corroborated = sum(item.get("status") == "CORROBORATED" for item in reconciliations)

    cards = st.columns(4)
    for column, label, value, note in [
        (cards[0], "Metric tracks", len(reconciliations), "in selected store"),
        (cards[1], "Evidence points", total_evidence, "source citations"),
        (cards[2], "Corroborated", corroborated, "aligned findings"),
        (cards[3], "Store", Path(st.session_state.selected_store).parent.name, "active corpus"),
    ]:
        with column:
            st.markdown(f'<div class="metric-card"><div class="metric-label">{esc(label)}</div><div class="metric-value">{esc(value)}</div><div class="metric-note">{esc(note)}</div></div>', unsafe_allow_html=True)

    st.markdown("<div class='section-label'>Findings explorer</div>", unsafe_allow_html=True)
    search_col, filter_col, sort_col = st.columns([2.3, 1.3, 1.2])
    with search_col:
        query = st.text_input("Search findings", placeholder="Search metric or synthesis…", label_visibility="collapsed")
    with filter_col:
        selected_statuses = st.multiselect("Status", statuses, default=statuses, label_visibility="collapsed", placeholder="Filter status")
    with sort_col:
        sort_mode = st.selectbox("Sort", ["Original order", "A–Z", "Evidence count"], label_visibility="collapsed")

    filtered: list[tuple[int, dict[str, Any]]] = []
    for index, item in enumerate(reconciliations):
        status = item.get("status", "UNRECONCILED")
        searchable = f"{item.get('metric_name', '')} {item.get('synthesis', '')}".lower()
        if status in selected_statuses and all(token in searchable for token in query.lower().split()):
            filtered.append((index, item))
    if sort_mode == "A–Z":
        filtered.sort(key=lambda pair: str(pair[1].get("metric_name", "")).lower())
    elif sort_mode == "Evidence count":
        filtered.sort(key=lambda pair: len(pair[1].get("data_points", [])), reverse=True)

    if not filtered:
        st.info("No findings match these filters.")
        st.stop()

    if "active_metric_idx" not in st.session_state or st.session_state.active_metric_idx not in {index for index, _ in filtered}:
        st.session_state.active_metric_idx = filtered[0][0]

    left, right = st.columns([0.9, 1.6], gap="large")
    with left:
        st.markdown(f"<div class='section-label' style='margin-top:0;'>{len(filtered)} matching tracks</div>", unsafe_allow_html=True)
        for index, item in filtered:
            status = item.get("status", "UNRECONCILED")
            active = index == st.session_state.active_metric_idx
            label = f"{item.get('metric_name', 'Untitled metric')}  ·  {status.replace('_', ' ').title()}"
            if st.button(label, key=f"metric_{index}", type="primary" if active else "secondary", use_container_width=True):
                st.session_state.active_metric_idx = index
                st.rerun()

    with right:
        active = reconciliations[st.session_state.active_metric_idx]
        # FIX (Bug 1): single st.markdown() call for the entire card — see render_detail_card().
        st.markdown(render_detail_card(active), unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Tab 3: Ingest & Reconcile (Live Streaming Console)
# -----------------------------------------------------------------------------
else:
    st.markdown('<div class="eyebrow">Corpus intelligence / 02</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="hero-title">Ingest & reconcile</h1>', unsafe_allow_html=True)
    st.markdown('<p class="hero-copy">Upload PDF excerpts, extract grounded facts, and reconcile recurring metrics across two or more source documents.</p>', unsafe_allow_html=True)

    st.markdown("<div class='section-label'>Pipeline</div>", unsafe_allow_html=True)
    st.markdown("**1. Upload**  →  **2. Extract facts**  →  **3. Reconcile evidence**", unsafe_allow_html=True)
    uploaded_files = st.file_uploader("PDF documents", type=["pdf"], accept_multiple_files=True, label_visibility="collapsed")

    if uploaded_files:
        st.info(f"{len(uploaded_files)} document(s) ready. Use at least two documents to generate a reconciliation store.")
        with st.expander("Review selected documents", expanded=True):
            for uploaded in uploaded_files:
                st.markdown(f"• `{esc(uploaded.name)}` · {uploaded.size / 1024:.1f} KB", unsafe_allow_html=True)

    run_pipeline = st.button("Run ingestion pipeline", type="primary", disabled=not uploaded_files, use_container_width=False)
    if run_pipeline:
        extracted_paths: list[str] = []
        errors: list[str] = []

        st.markdown("<div class='section-label'>Live Execution Terminal</div>", unsafe_allow_html=True)
        log_box = st.empty()
        streamer = TerminalLogStreamer(log_box)
        old_stdout = sys.stdout

        try:
            sys.stdout = streamer
            with st.status("Executing pipeline across documents…", expanded=True) as progress:
                for uploaded in uploaded_files:
                    try:
                        target_pdf = save_uploaded_file(uploaded)
                        output_json = FACTS_DIR / f"{target_pdf.stem}_facts.json"

                        print(f"\n[Ingesting] {uploaded.name}")
                        facts = extract_facts_from_pdf(str(target_pdf), max_chunks=3)
                        with output_json.open("w", encoding="utf-8") as file:
                            json.dump([fact.model_dump() for fact in facts], file, indent=2, ensure_ascii=False)
                        extracted_paths.append(str(output_json))
                        print(f"-> Successfully indexed {len(facts)} facts to {output_json.name}")
                    except Exception as exc:
                        errors.append(f"{uploaded.name}: {exc}")
                        print(f"[Error] {uploaded.name}: {exc}")

                if len(extracted_paths) >= 2:
                    print("\n[Synthesizing] Reconciling facts across documents...")
                    results = run_multi_document_reconciliation(extracted_paths)
                    reconciliation_file = RECON_DIR / "reconciliation_results.json"
                    with reconciliation_file.open("w", encoding="utf-8") as file:
                        json.dump([result.model_dump() for result in results], file, indent=2, ensure_ascii=False)
                    print(f"-> Generated {len(results)} reconciled tracks in {reconciliation_file.name}")
                    progress.update(label="Pipeline run completed!", state="complete")
                else:
                    progress.update(label="Extraction complete; reconciliation requires at least two documents", state="complete")
        finally:
            sys.stdout = old_stdout

        if errors:
            for error in errors:
                st.error(error)
        if len(extracted_paths) >= 2:
            st.session_state.selected_store = f"{RECON_DIR.name}/reconciliation_results.json"
            st.success("Documents processed successfully. Switch to Audit findings to inspect.")
            st.rerun()
        elif extracted_paths:
            st.warning("Facts were extracted, but reconciliation was skipped because fewer than two documents completed successfully.")

    st.markdown("<div class='section-label'>Output locations</div>", unsafe_allow_html=True)
    st.caption(
        f"Uploaded PDFs: `{DATA_DIR.relative_to(ROOT_DIR)}`  ·  "
        f"Raw facts: `{FACTS_DIR.relative_to(ROOT_DIR)}`  ·  "
        f"Reconciliations: `{RECON_DIR.relative_to(ROOT_DIR)}`"
    )

    if stores:
        st.markdown("<div class='section-label'>Existing stores</div>", unsafe_allow_html=True)
        # FIX (dark-mode glitch): st.dataframe() is a native widget rendered in
        # its own iframe with an independent theme system — it doesn't read
        # our injected CSS variables, so it can end up on a different light/dark
        # theme than the rest of the app. Rendering as plain HTML keeps it in
        # sync with the app's own theme toggle.
        rows_html = "".join(
            f'<tr>'
            f'<td style="padding:.6rem .9rem; border-bottom:1px solid {COLORS["border"]}; color:{COLORS["text"]};">{esc(name)}</td>'
            f'<td style="padding:.6rem .9rem; border-bottom:1px solid {COLORS["border"]}; color:{COLORS["muted"]}; font-family:\'DM Mono\',monospace; font-size:.82rem;">{esc(path.relative_to(ROOT_DIR))}</td>'
            f'</tr>'
            for name, path in stores.items()
        )
        table_html = (
            f'<div style="border:1px solid {COLORS["border"]}; border-radius:10px; overflow:hidden; background:{COLORS["surface"]};">'
            '<table style="width:100%; border-collapse:collapse;">'
            '<thead><tr>'
            f'<th style="text-align:left; padding:.6rem .9rem; background:{COLORS["surface_alt"]}; color:{COLORS["muted"]}; font:600 .72rem \'DM Mono\',monospace; text-transform:uppercase; letter-spacing:.06em;">Store</th>'
            f'<th style="text-align:left; padding:.6rem .9rem; background:{COLORS["surface_alt"]}; color:{COLORS["muted"]}; font:600 .72rem \'DM Mono\',monospace; text-transform:uppercase; letter-spacing:.06em;">Path</th>'
            '</tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            '</table>'
            '</div>'
        )
        st.markdown(table_html, unsafe_allow_html=True)

st.caption("FactStore · Evidence-first document reconciliation")