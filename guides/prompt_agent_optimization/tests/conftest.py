import sys
from pathlib import Path

# Add parent directory to sys.path so tests can import optimization_guide
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
