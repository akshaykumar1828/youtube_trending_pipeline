"""Build-time only: refuse to build an image whose model artifacts differ from the frozen
checksums in tests/fixtures/artifact_sha256.json.

Usage: python verify_artifacts.py <model_dir> <artifact_sha256.json>
"""

import hashlib
import json
import sys
from pathlib import Path

# Exactly the files ml/inference.py loads. The notebook, README and urgency_words.txt (not read
# by ml/) are not shipped.
REQUIRED = ["clip_values.pkl", "meta_lr.pkl", "ohe.pkl", "psych_lr.pkl", "psych_scaler.pkl",
            "rf_calibrated.pkl", "text_lr.pkl", "text_scaler.pkl"]

model_dir, manifest = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())["files"]
shipped = sorted(p.name for p in model_dir.iterdir())
if shipped != sorted(REQUIRED):
    sys.exit(f"unexpected model directory contents: {shipped}")
for name in REQUIRED:
    if hashlib.sha256((model_dir / name).read_bytes()).hexdigest() != manifest[name]:
        sys.exit(f"artifact checksum mismatch: {name}")
print(f"{len(REQUIRED)} frozen model artifacts verified")
