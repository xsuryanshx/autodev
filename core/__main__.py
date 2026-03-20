"""Allow ``python -m core`` to invoke the CLI."""
from core.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
