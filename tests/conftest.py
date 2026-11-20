from __future__ import annotations

import os

# GUI tests exercise Qt signal/thread behavior without invoking Windows shell,
# accessibility, or display COM services from an unattended test process.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
