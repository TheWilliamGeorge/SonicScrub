#!/usr/bin/env python3
"""
SonicScrub — Entry point.
Launch the SonicScrub desktop application.
"""

import os
# Prevent Intel Mac openMP crash
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def main():
    from gui import SonicScrubApp

    app = SonicScrubApp()
    app.protocol ("WM_DELETE_WINDOW", lambda: app.destroy())
    app.mainloop()


if __name__ == "__main__":
    main()
