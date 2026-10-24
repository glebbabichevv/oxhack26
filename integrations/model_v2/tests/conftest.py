import os
os.environ.setdefault("OMP_NUM_THREADS", "1")

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
