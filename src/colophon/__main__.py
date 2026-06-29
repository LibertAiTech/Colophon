"""Module entry point for ``python -m colophon``.

Delegates to ``cli.main()``, where CLI arguments become a project and command
dispatch enters build, serve, deploy, or scaffold dataflow.
"""

from __future__ import annotations

import sys

from .cli import main


if __name__ == "__main__":
    sys.exit(main())
