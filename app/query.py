import sys
import json
from pathlib import Path

DB_ROOT = Path(__file__).resolve().parent.parent / "db"


def find_available_reconciliations() -> dict[str, Path]:
    """Dynamically finds all reconciliation JSON files across the db directory."""
    files = {}
    if not DB_ROOT.exists():
        return files
    for p in DB_ROOT.rglob("*.json"):
        if "reconcil" in p.name.lower():
            label = f"{p.parent.name}/{p.name}"
            files[label] = p
    return files


def search_file(recon_path: Path, query: str):
    if not recon_path.exists():
        print(f"Error: Could not find reconciliation file at {recon_path}")
        return

    with open(recon_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    query_tokens = query.lower().strip().split()
    matches = []

    for item in data:
        # Match query terms against metric name or synthesis explanation
        target_text = f"{item.get('metric_name', '')} {item.get('synthesis', '')}".lower()
        if any(token in target_text for token in query_tokens):
            matches.append(item)

    if not matches:
        print(f"\nNo reconciled metrics matched '{query}'.")
        print("\nAvailable metrics in this store:")
        for idx, item in enumerate(data, 1):
            print(f"  {idx}. {item.get('metric_name', 'Unknown')} [{item.get('status', 'N/A')}]")
        return

    print(f"\nFound {len(matches)} matching metric track(s) in [{recon_path.name}]:\n" + "=" * 70)
    for m in matches:
        print(f"\nMETRIC: {m.get('metric_name')}")
        print(f"STATUS: [{m.get('status')}]")
        print(f"SYNTHESIS:\n  {m.get('synthesis')}\n")
        print("AUDIT EVIDENCE POINTS:")
        for dp in m.get("data_points", []):
            period = f" | Period: {dp['time_period']}" if dp.get("time_period") else ""
            print(f"  * [{dp.get('source_doc')} - Page {dp.get('page_num')}]")
            print(f"    Value   : {dp.get('value')}{period}")
            print(f"    Citation: \"{dp.get('evidence_text')}\"")
        print("-" * 70)


def interactive_cli(recon_path: Path):
    print("==================================================")
    print(f"   Corpus Audit Query CLI: {recon_path.parent.name}/{recon_path.name}")
    print("==================================================")
    print("Type a metric keyword (or 'exit' to quit).\n")
    while True:
        try:
            user_input = input("query> ").strip()
            if not user_input or user_input.lower() in ["exit", "quit", "q"]:
                break
            search_file(recon_path, user_input)
        except (KeyboardInterrupt, EOFError):
            break


if __name__ == "__main__":
    available = find_available_reconciliations()

    # Case 1: Direct path or file passed as CLI argument
    if len(sys.argv) >= 2 and sys.argv[1].endswith(".json"):
        recon_target = Path(sys.argv[1])
        if len(sys.argv) > 2:
            search_file(recon_target, " ".join(sys.argv[2:]))
        else:
            interactive_cli(recon_target)
        sys.exit(0)

    # Case 2: Default discovery from db/
    if not available:
        print(f"No reconciliation files found inside {DB_ROOT}.")
        print("Run compare.py first to generate a reconciliation file.")
        sys.exit(1)

    # If only one reconciliation exists, use it directly; otherwise let user pick
    if len(available) == 1:
        chosen_path = list(available.values())[0]
    else:
        print("\nAvailable Reconciliation Stores:")
        keys = list(available.keys())
        for idx, k in enumerate(keys, 1):
            print(f"  [{idx}] {k}")
        choice = input("\nSelect a corpus number (default 1): ").strip()
        idx = int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= len(keys) else 0
        chosen_path = available[keys[idx]]

    # Search keyword passed directly after filename
    if len(sys.argv) >= 2 and not sys.argv[1].endswith(".json"):
        search_file(chosen_path, " ".join(sys.argv[1:]))
    else:
        interactive_cli(chosen_path)