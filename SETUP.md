# Ejecutar YitetsuAI

Python 3.12, Node.js 24 y Linux. El proceso de extracción usa límites POSIX;
para Windows utiliza Docker o WSL. Para desarrollo fuera de Docker se necesitan
FFmpeg/FFprobe, Tesseract (idiomas español e inglés) y Poppler (`pdftoppm`).

## Docker: API y servicios

```bash
docker compose up -d --build
make pull-model
```

Esto descarga `qwen2.5:0.5b` para texto y `moondream` para imágenes. Puedes cambiar
`OLLAMA_MODEL` y `OLLAMA_VISION_MODEL` por modelos compatibles, según los recursos
y la precisión requerida. La primera extracción de audio descarga Whisper `tiny`;
puedes cambiar `WHISPER_MODEL` a otro modelo o a una ruta local ya preparada.
Los modelos no forman parte del repositorio. Descargarlos requiere acceso a
`registry.ollama.ai`, sus blobs `*.r2.cloudflarestorage.com`, `huggingface.co` y los
hosts de almacenamiento de Hugging Face (`*.xethub.hf.co`, `*.huggingface.co`).
Mantén la verificación TLS y configura la CA del entorno si la red usa un proxy.

La API escucha en `127.0.0.1:8001` para no interferir con otros proyectos que
usen el puerto 8000. PostgreSQL guarda usuarios, sesiones, conversaciones,
mensajes, fuentes, extracciones y auditoría. Originales/derivados se conservan en
`attachments_data`; Whisper en `whisper_data`; Ollama en `ollama_data`.
La API crea tablas nuevas y añade `updated_at` y `sources` a instalaciones
PostgreSQL anteriores sin borrar conversaciones existentes. `init.sql` se aplica
solo al crear el volumen PostgreSQL por primera vez.

Para arrancar la interfaz:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1
```

`VITE_API_URL` controla la dirección pública de la API; por defecto
`http://127.0.0.1:8001`. El frontend local escucha en `127.0.0.1:5174`; los
puertos 5173 y 8000 quedan libres.
El navegador debe poder llegar a esa dirección. Configura CORS si cambias el
origen de la web. Los puertos locales son para desarrollo, no un despliegue público.

```bash
docker compose down
```

`make down` también conserva datos. `docker compose down -v` elimina los volúmenes,
incluidos todos los adjuntos y conversaciones. El Compose heredado conserva sus
credenciales PostgreSQL de desarrollo; configura credenciales, TLS y acceso a
los puertos antes de usarlo como servicio público.

## Desarrollo local

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p data
DATABASE_URL=sqlite+aiosqlite:///./data/dev.db .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8001
```

SQLite sirve para desarrollo y pruebas en una base nueva. Para la aplicación con
persistencia PostgreSQL, usa el servicio Compose o define `DATABASE_URL` con tu
conexión. `.env` se carga sin sobrescribir variables exportadas. Conserva secretos
y datos fuera de Git. La inferencia necesita Ollama en `OLLAMA_URL` (por defecto
http://127.0.0.1:11434) y los modelos instalados. `/health` comprueba la API,
no la disponibilidad de los modelos.

## Pruebas

```bash
make test
cd frontend
npm run build
CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e
```

Sin Chromium disponible: `npx playwright install chromium` y luego `npm run test:e2e`
sin `CHROMIUM_PATH`. La suite de API usa SQLite temporal y un modelo controlado;
la extracción de documentos/OCR/video usa los parsers y herramientas reales.
El navegador prueba el flujo contra respuestas API controladas. Consulta
[los límites y la cobertura de validación](docs/attachments.md).

La interpretación conserva puntuación, detecta español/inglés con diccionarios y
corrige errores comunes o inequívocos. Devuelve `interpreted_prompt` y `corrections`;
los mensajes guardan el texto original. Los principios de ayuda humana,
incertidumbre y límites forman parte de las instrucciones del modelo; no se
presentan como una certificación ética automática. `documents`/pgvector y Redis
siguen disponibles en el esquema/Compose heredados; el flujo de adjuntos actual
no realiza búsqueda vectorial ni usa Redis.

## Componentes básicos de IA

`GET /ai/capabilities` describe los diez componentes que coordinan la consulta:
interpretación/corrección, intención/idioma, memoria conversacional, lectura de
documentos, análisis tabular, recuperación de fragmentos, percepción
multimodal, generación de lenguaje, fuentes/transparencia y seguridad/manejo de
fallos. Estos son componentes especializados del pipeline, no diez LLM grandes.
La generación y percepción visual requieren los modelos configurados en Ollama;
la extracción de audio, video y OCR puede requerir herramientas locales
adicionales. El endpoint informa requisitos, no certifica que modelos externos
estén descargados o respondiendo.
