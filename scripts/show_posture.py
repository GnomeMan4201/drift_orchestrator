#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import json
from firewall.sensation import collect_state, derive_posture, build_policy_header

state = collect_state()
posture = derive_posture(state)

print(json.dumps({
    "state": state.to_dict(),
    "posture": posture.to_dict(),
    "policy_header": build_policy_header(posture, state),
}, indent=2))
