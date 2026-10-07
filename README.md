Contruccion de mi AI 

*Pensamiento criticos y predictibles*
*Razonamiento en contrastes Humanos*
*Peticiones las cuales puedan ser usadas como guias o ayudas de actividades o proyectos*
*Limitaciones en las tareas mas complejas por valores propios de la AI*

prueba de error

## Estado del MVP

El MVP añade una API FastAPI y un frontend React en `frontend/`. Para ejecutarlo
con persistencia PostgreSQL, sigue las instrucciones de [SETUP.md](SETUP.md).
Los usuarios, sesiones, conversaciones, mensajes y eventos de auditoría se
guardan en PostgreSQL; las conversaciones solo se guardan cuando el usuario
inicia sesión.
## Adjuntos multimodales

La IA acepta PDF, DOCX, XLSX, CSV/TSV, JSON, texto, HTML/XML, imágenes, audio y
video. Cada archivo se extrae según su tipo y queda asociado a su usuario y
conversación. La interfaz permite seleccionar adjuntos, descargarlos, eliminarlos
y revisar las fuentes aportadas al modelo. Las consultas generales usan Ollama
con contexto e historial; imágenes usan visión y audio usa Whisper.

Consulta [arquitectura, formatos y límites](docs/attachments.md) y
[instalación de servicios y modelos](SETUP.md).
