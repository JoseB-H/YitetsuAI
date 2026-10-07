import os
from pathlib import Path
import re
import uuid

MAX_BYTES = 25 * 1024 * 1024
MAX_PER_CONVERSATION = 20
EXTENSIONS = {
    ".txt": "text",
    ".md": "text",
    ".log": "text",
    ".csv": "table",
    ".tsv": "table",
    ".json": "structured",
    ".html": "html",
    ".htm": "html",
    ".xml": "xml",
    ".pdf": "pdf",
    ".docx": "word",
    ".xlsx": "spreadsheet",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".gif": "image",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".ogg": "audio",
    ".flac": "audio",
    ".mp4": "video",
    ".mov": "video",
    ".webm": "video",
    ".mkv": "video",
}


def storage_root():
    root = Path(os.getenv("ATTACHMENT_DIR", "data/attachments")).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    return root


def folder(identifier):
    return storage_root() / str(uuid.UUID(str(identifier)))


def safe_filename(filename):
    name = (filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(c for c in name if c.isprintable()).strip()[:255]
    if not name:
        raise ValueError("El archivo necesita un nombre y extensión")
    extension = Path(name).suffix.lower()
    if extension not in EXTENSIONS:
        raise ValueError(
            "Formato no compatible. Usa documentos, tablas, imágenes, audio o video admitidos."
        )
    return name, extension, EXTENSIONS[extension]


def derivative_path(identifier, name):
    if not re.fullmatch(r"visual-[0-9]+\.jpg", name):
        raise ValueError("Ruta visual inválida")
    return folder(identifier) / name
