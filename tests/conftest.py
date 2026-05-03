import sys
from pathlib import Path

# Add project root to sys.path so all test modules can import calibration,
# orchestrator, replay_cli, etc. without sys.path hacks in each file.
sys.path.insert(0, str(Path(__file__).parent.parent))
