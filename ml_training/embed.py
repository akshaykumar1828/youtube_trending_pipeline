"""LaBSE embeddings, computed once per text variant and cached in cache/emb_<variant>.npy.

The same pinned LaBSE revision as the app (deploy/labse) is used, in float32, with the default
256-token limit, so v2 sees exactly what serving will see.
"""

import throttle  # noqa: F401  (first: thread limits)

import hashlib
import json
import time

import numpy as np

from common import CACHE

LABSE = "sentence-transformers/LaBSE"
LABSE_REVISION = "836121a0533e5664b21c7aacc5d22951f2b8b25b"
_model = None


def _embedder():
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer
        throttle.limit_torch()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = SentenceTransformer(LABSE, device=device, revision=LABSE_REVISION)
        print(f"LaBSE on {device}, max_seq_length={_model.max_seq_length}", flush=True)
    return _model


def _fingerprint(texts):
    h = hashlib.sha256()
    for t in texts:
        h.update(t.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def embeddings(variant, texts, batch_size=None):
    """float32 array (len(texts), 768). Recomputed only if the texts changed.
    Encoded in chunks with a short pause after each, to limit GPU heat."""
    path, meta_path = CACHE / f"emb_{variant}.npy", CACHE / f"emb_{variant}.json"
    fp = _fingerprint(texts)
    if path.exists() and meta_path.exists() and json.loads(meta_path.read_text())["fingerprint"] == fp:
        return np.load(path)
    model = _embedder()
    batch_size = batch_size or throttle.GPU_BATCH
    started = time.time()
    parts = []
    for i in range(0, len(texts), throttle.GPU_CHUNK):
        parts.append(model.encode(texts[i:i + throttle.GPU_CHUNK], batch_size=batch_size,
                                  convert_to_numpy=True, show_progress_bar=False).astype(np.float32))
        done = min(i + throttle.GPU_CHUNK, len(texts))
        if done < len(texts):
            if (i // throttle.GPU_CHUNK) % 10 == 0:
                print(f"  {variant}: {done}/{len(texts)} ({time.time() - started:.0f}s)", flush=True)
            time.sleep(throttle.GPU_CHUNK_PAUSE)
    emb = np.vstack(parts)
    np.save(path, emb)
    meta_path.write_text(json.dumps({"fingerprint": fp, "n": len(texts), "seconds": round(time.time() - started, 1),
                                     "revision": LABSE_REVISION}))
    print(f"embedded {variant}: {len(texts)} texts in {time.time() - started:.0f}s", flush=True)
    return emb
