"""Build-time only: refuse to build an image whose model file differs from the checksum in
tests/fixtures/artifact_sha256.json (the model that was evaluated in ml_training/REPORT.md).

Usage: python verify_artifacts.py <model_dir> <artifact_sha256.json>
"""

import hashlib
import json
import sys
from pathlib import Path

# Exactly the file ml/inference.py loads.
REQUIRED = ["trending_model_v3.joblib"]

model_dir, manifest = Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text())["files"]
shipped = sorted(p.name for p in model_dir.iterdir())
if shipped != sorted(REQUIRED):
    sys.exit(f"unexpected model directory contents: {shipped}")
for name in REQUIRED:
    if hashlib.sha256((model_dir / name).read_bytes()).hexdigest() != manifest[name]:
        sys.exit(f"model checksum mismatch: {name}")
print(f"{len(REQUIRED)} model file verified")
