"""Allow ``python -m aegisai`` during local smoke checks."""

from .main import main

raise SystemExit(main())
