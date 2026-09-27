"""Root scripts.train module forwarding to python.scripts.train."""
from __future__ import annotations

import sys
from pathlib import Path

_python_scripts_dir = Path(__file__).resolve().parent.parent / "python" / "scripts"
if str(_python_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_python_scripts_dir))

try:
    from train import (  # type: ignore
        FEEDBACK_CONTRACT_VERSION,
        build_training_metadata,
        run_epoch,
        set_seed,
    )
except ImportError:
    # If python is on path as package
    from python.scripts.train import (  # type: ignore
        FEEDBACK_CONTRACT_VERSION,
        build_training_metadata,
        run_epoch,
        set_seed,
    )
