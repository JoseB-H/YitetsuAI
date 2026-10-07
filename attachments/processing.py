import asyncio
import json
from pathlib import Path
import subprocess
import sys
from attachments.extract import ExtractionError

slots = asyncio.Semaphore(1)


def run_worker(path, kind):
    output = path.parent / "extraction.json"
    try:
        response = subprocess.run(
            [sys.executable, "-m", "attachments.worker", str(path), kind, str(output)],
            capture_output=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExtractionError(
            "Se agotó el tiempo de procesamiento. Divide el archivo en partes más pequeñas."
        ) from exc
    if not output.exists():
        raise ExtractionError(
            "No se pudo procesar el archivo dentro del límite de recursos"
        )
    result = json.loads(output.read_text())
    if response.returncode or "error" in result:
        raise ExtractionError(result.get("error", "No se pudo procesar el archivo"))
    return result


async def process_file(path, kind):
    async with slots:
        return await asyncio.to_thread(run_worker, path, kind)
