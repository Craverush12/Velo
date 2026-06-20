"""Run this to verify coverage of the test file across all dimensions."""

import json
from collections import Counter
from pathlib import Path

TEST_FILE = Path(__file__).parent / "ideal_test_cases.json"

with open(TEST_FILE, encoding="utf-8") as f:
    cases = json.load(f)

print(f"Total cases: {len(cases)}\n")

for dim in ("icp", "domain", "intent", "mode", "context_richness"):
    counts = Counter(c.get(dim, "MISSING") for c in cases)
    print(f"{dim}:")
    for val, n in sorted(counts.items()):
        print(f"  {val:<35} {n}")
    print()

# Check all 6 intents covered
intents_covered = set(c.get("intent") for c in cases)
all_intents = {"inquiry", "construction", "debugging", "decision", "operation", "chat"}
missing_intents = all_intents - intents_covered
print(f"Intents covered: {sorted(intents_covered)}")
if missing_intents:
    print(f"  ⚠ MISSING: {missing_intents}")
else:
    print("  ✓ All 6 intents covered")

# Check domains
domains_covered = set(c.get("domain") for c in cases)
print(f"\nDomains covered ({len(domains_covered)}): {sorted(domains_covered)}")

# Check ICPs
icps_covered = set(c.get("icp") for c in cases)
print(f"\nICPs covered: {sorted(icps_covered)}")
