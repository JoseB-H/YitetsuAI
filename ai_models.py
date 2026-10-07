from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AICapability:
    id: str
    name: str
    function: str
    implementation: str
    availability: str


CAPABILITIES = (
    AICapability(
        "interpretation",
        "Interpretación y corrección",
        "Corrige errores inequívocos antes de responder y conserva el texto original.",
        "Corrector local ES/EN",
        "integrado",
    ),
    AICapability(
        "intent",
        "Intención y lenguaje",
        "Atiende saludos e identidad directamente y mantiene el idioma de la consulta.",
        "Reglas locales + instrucciones del modelo",
        "integrado",
    ),
    AICapability(
        "memory",
        "Memoria conversacional",
        "Usa los últimos mensajes de la conversación elegida como contexto.",
        "Historial privado persistente",
        "integrado",
    ),
    AICapability(
        "documents",
        "Lectura de documentos",
        "Extrae contenido de PDF, Office, texto, tablas, JSON y páginas web.",
        "Procesadores locales con límites",
        "integrado",
    ),
    AICapability(
        "structured_data",
        "Análisis de datos tabulares",
        "Procesa CSV/Excel y calcula resúmenes acotados para evitar fingir análisis completo.",
        "Extracción local por filas y hojas",
        "integrado",
    ),
    AICapability(
        "retrieval",
        "Búsqueda de contexto",
        "Prioriza fragmentos relacionados con la consulta y conserva sus localizadores.",
        "Recuperación por términos + presupuesto",
        "integrado",
    ),
    AICapability(
        "multimodal",
        "Percepción de imagen, audio y video",
        "Combina OCR/transcripción y fotogramas muestreados; advierte lo que pudo omitirse.",
        "Tesseract, FFmpeg, Whisper y modelo visual",
        "requiere herramientas/modelos externos",
    ),
    AICapability(
        "generation",
        "Generación de lenguaje",
        "Redacta respuestas con contexto y sin respuestas sintéticas si el modelo falla.",
        "Ollama + qwen2.5:0.5b por defecto",
        "requiere Ollama y modelo instalado",
    ),
    AICapability(
        "provenance",
        "Fuentes y transparencia",
        "Devuelve fragmentos y advertencias para ayudar a verificar las respuestas.",
        "Fuentes por archivo/página/fila/tiempo",
        "integrado; las fuentes no garantizan exactitud",
    ),
    AICapability(
        "safety",
        "Seguridad y manejo de fallos",
        "Trata adjuntos como datos no confiables, limita recursos y registra acciones.",
        "Guardas de instrucciones, límites y auditoría",
        "integrado",
    ),
)


def list_capabilities() -> list[dict[str, str]]:
    return [asdict(capability) for capability in CAPABILITIES]
