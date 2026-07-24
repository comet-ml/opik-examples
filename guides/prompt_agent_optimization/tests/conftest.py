import os
import sys
from pathlib import Path

# Disable Opik tracking during tests: the @opik.track-decorated rag_app
# functions would otherwise flush spans to the backend at teardown and, with no
# credentials in the test env, emit 401 noise after the pytest summary.
os.environ.setdefault("OPIK_TRACK_DISABLE", "true")

# Add parent directory to sys.path so tests can import optimization_guide
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
