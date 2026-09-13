"""PyInstaller entry point for the self-contained ChronoSync CLI build."""

from __future__ import annotations

import sys

from chronosync.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
