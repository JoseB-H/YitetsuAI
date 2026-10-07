"""Subprocess boundary: bounded time/memory; private content is written to a result file."""

import json
import os
from pathlib import Path
import resource
import sys

if __name__ == "__main__":
    resource.setrlimit(resource.RLIMIT_AS, (6 * 1024**3, 6 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (170, 170))
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024**2, 100 * 1024**2))
    os.environ["OMP_NUM_THREADS"] = "2"
    os.environ["OPENBLAS_NUM_THREADS"] = "2"
    os.environ["MKL_NUM_THREADS"] = "2"
    from attachments.extract import extract, ExtractionError

    path, kind, output = sys.argv[1:]
    try:
        result = extract(Path(path), kind)
    except ExtractionError as exc:
        Path(output).write_text(json.dumps({"error": str(exc)}))
        sys.exit(2)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, default=str))
