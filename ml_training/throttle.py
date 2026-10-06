"""Load limits for running on a laptop (keeps temperatures down). Import this FIRST, before
numpy / scikit-learn / torch, because thread pools are sized when those libraries load.

Override with environment variables if needed: ML_THREADS, ML_GPU_BATCH, ML_STAGE_PAUSE.
Limiting threads changes speed only, not results (all randomness is seeded).
"""

import os
import time

THREADS = int(os.environ.get("ML_THREADS", "6"))           # of 12 logical cores
GPU_BATCH = int(os.environ.get("ML_GPU_BATCH", "32"))      # LaBSE batch size (was 128)
GPU_CHUNK = 2048                                           # texts between GPU pauses
GPU_CHUNK_PAUSE = 2.0                                      # seconds
STAGE_PAUSE = float(os.environ.get("ML_STAGE_PAUSE", "60"))  # seconds between stages
FIT_PAUSE = 3.0                                            # seconds between grid-search fits

for var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
            "VECLIB_MAXIMUM_THREADS", "LOKY_MAX_CPU_COUNT"):
    os.environ[var] = str(THREADS)


def limit_torch():
    import torch
    torch.set_num_threads(THREADS)
    torch.set_num_interop_threads(max(1, THREADS // 2))


def pause(seconds, why=""):
    if seconds > 0:
        print(f"[pause {seconds:.0f}s{(' - ' + why) if why else ''}]", flush=True)
        time.sleep(seconds)
