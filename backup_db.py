#!/usr/bin/env python3
"""Backup garage-library.db to /Users/matthewtrump/Developer/databases."""

import shutil
import sys
from datetime import datetime
from pathlib import Path

SRC = Path(__file__).parent / "garage-library.db"
DEST_DIR = Path("/Users/matthewtrump/Developer/databases")


def main():
    if not SRC.exists():
        print(f"Error: source database not found: {SRC}", file=sys.stderr)
        sys.exit(1)

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = DEST_DIR / f"garage-library_{timestamp}.db"

    shutil.copy2(SRC, dest)
    print(f"Backed up to {dest}")


if __name__ == "__main__":
    main()
