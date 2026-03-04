"""Allow running the publisher as: python -m publisher --capture-dir ..."""

import sys

from publisher.cli import main

sys.exit(main())
