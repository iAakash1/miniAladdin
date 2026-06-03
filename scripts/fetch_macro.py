#!/usr/bin/env python3
"""
OmniSignal Macro Fetch Script
Standalone CLI to pull FRED macro data and compute the Systemic Risk Multiplier.

Usage:
    python scripts/fetch_macro.py
    python scripts/fetch_macro.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path so we can import src/
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

from src.risk_analysis import OmniSignalRiskEngine


def main():
    parser = argparse.ArgumentParser(
        description="Fetch macro-economic data from FRED and compute Systemic Risk Multiplier"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output as JSON (default: human-readable)"
    )
    parser.add_argument(
        "--api-key", type=str, default=None, help="FRED API key (overrides .env)"
    )
    args = parser.parse_args()

    engine = OmniSignalRiskEngine(api_key=args.api_key)
    multiplier, stats = engine.get_systemic_risk_multiplier()

    output = {
        "risk_multiplier": multiplier,
        **stats,
    }

    if args.json:
        print(json.dumps(output, indent=2, default=str))
    else:
        print("=" * 50)
        print("  OmniSignal — Macro Risk Assessment")
        print("=" * 50)
        print(f"  Risk Multiplier : {multiplier}")
        for key, value in stats.items():
            print(f"  {key:<20}: {value}")
        print("=" * 50)

        # Interpretation
        if multiplier > 1.3:
            print("\n  ⚠️  CRITICAL: Macro conditions are unfavorable.")
            print("  Bullish predictions will be heavily dampened.")
        elif multiplier > 1.1:
            print("\n  🟡  ELEVATED: Some macro headwinds present.")
            print("  Bullish predictions will be moderately dampened.")
        else:
            print("\n  🟢  STABLE: Macro environment is favorable.")
            print("  No dampening applied to predictions.")


if __name__ == "__main__":
    main()
