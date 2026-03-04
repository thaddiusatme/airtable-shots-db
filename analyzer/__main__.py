"""Allow running the analyzer as: python -m analyzer --capture-dir ..."""

import sys

from analyzer.analyze import main

sys.exit(main())
