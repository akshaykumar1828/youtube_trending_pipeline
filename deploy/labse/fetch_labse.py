"""Build-time only: put the exact LaBSE revision the frozen model was validated with into a
Hugging Face cache directory, verified file by file against labse.sha256.

The API container then runs with HF_HUB_OFFLINE=1, so it never downloads (or silently
upgrades) the text encoder at runtime. ml/inference.py is unchanged: it still loads
"sentence-transformers/LaBSE", which resolves to this cached revision.

Usage: python fetch_labse.py <cache_dir> <sha256_manifest>
"""

import hashlib
import sys
from pathlib import Path

from huggingface_hub import snapshot_download

REPO = "sentence-transformers/LaBSE"
REVISION = "836121a0533e5664b21c7aacc5d22951f2b8b25b"  # same snapshot as the Phase 1 reference outputs


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main(cache_dir: str, manifest: str) -> None:
    expected = dict(reversed(line.split("  ", 1)) for line in Path(manifest).read_text().splitlines() if line)
    snapshot = Path(snapshot_download(REPO, revision=REVISION, cache_dir=cache_dir,
                                      allow_patterns=sorted(expected)))
    present = {p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file()}
    if present != set(expected):
        sys.exit(f"LaBSE file set mismatch: missing={set(expected) - present} extra={present - set(expected)}")
    for name, digest in sorted(expected.items()):
        if sha256(snapshot / name) != digest:
            sys.exit(f"LaBSE checksum mismatch: {name}")
    # Offline loading of the model *name* resolves refs/main; point it at the pinned commit.
    refs = snapshot.parent.parent / "refs"
    refs.mkdir(exist_ok=True)
    (refs / "main").write_text(REVISION)
    print(f"LaBSE {REVISION}: {len(expected)} files verified")


if __name__ == "__main__":
    main(*sys.argv[1:])
