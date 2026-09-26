"""Compatibility shim — the generalised builder is catalog.build_package (R1-03)."""
from catalog.build_package import *  # noqa: F401,F403
from catalog.build_package import main

if __name__ == "__main__":
    raise SystemExit(main())
