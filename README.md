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