# Technical Brief - lab10_project

> Brief de producto: qué es `lab10_project` y qué hace. El detalle de los mecanismos internos
> vive en `docs/implementation-summary.md`; la guía para agregar herramientas o integraciones
> nuevas vive en `docs/extending.md`.

## 1) Qué es lab10_project

`lab10_project` es una plantilla de agente conversacional genérico y extensible: un chat web
con memoria de largo plazo, confirmación humana (HITL) para acciones riesgosas, y un punto de
extensión de herramientas que permite agregar integraciones nuevas — incluyendo servidores
MCP — sin reescribir el runtime del grafo.

Stack: FastAPI + LangGraph + Supabase + OpenRouter + Langfuse, UI SSR en Jinja2/HTMX.

## 2) Capacidades del producto

- Autenticación web (login, signup, logout) y onboarding guiado de 4 pasos.
- Chat web multi-sesión con sidebar, título automático, archivado y eliminación.
- Memoria de largo plazo (episódica, semántica, procedural) inyectada en el prompt antes de
  cada turno, con filtro de privacidad.
- Compactación de contexto en dos etapas para conversaciones largas, con circuit breaker.
- Confirmación humana (HITL) obligatoria para acciones de riesgo medio/alto, con tracking de
  ejecución para todas las tools.
- Catálogo de herramientas extensible por catálogo + adapter (sin tocar el grafo), con punto
  de extensión MCP.
- Adjuntos multimodales (imagen) y selector de modelo por usuario.
- Búsqueda de propiedades en venta/arriendo en Cali (`search_properties`), contra un
  proyecto Supabase separado del de la app, de solo lectura.
- Trazabilidad vía Langfuse y evaluaciones automatizadas contra el runtime real.

## 3) Arquitectura del producto

Separación por capas:

- `app/routers` y `app/pages`: entrada HTTP y contratos HTMX/SSR.
- `app/agent`: runtime LangGraph.
- `app/tools`: catálogo, schemas y adapters.
- `app/db`: acceso a Supabase y queries.
- `app/services`: servicios transversales.

Grafo canónico (invariante del producto): `memory_injection` y `compaction` corren en
paralelo desde `START` y confluyen en `agent`. Si el turno del modelo trae `tool_calls`,
`agent` rutea a `tools_auto` (ejecuta directo las tools que no requieren confirmación) y de
ahí siempre a `tools_confirm` (resuelve, como máximo, una tool que requiera confirmación por
invocación del grafo — si el batch trae varias, vuelve a rutear a sí mismo hasta resolverlas
todas). Cerrado ese batch, el flujo vuelve a `compaction -> agent` para la siguiente ronda, o
termina en `END` cuando el modelo responde sin más `tool_calls`:

```text
START -> memory_injection ┐
START -> compaction       ┴-> agent -> END (sin tool_calls)
                                agent -> limit_reached -> END (límite de iteraciones alcanzado)
                                agent -> tools_auto -> tools_confirm -> tools_confirm (loop, batch con 2+ confirmaciones)
                                                                     -> compaction -> agent (siguiente ronda)
```

## 4) Contrato de rutas (web + API)

| Método + ruta | Tipo | Respuesta |
| --- | --- | --- |
| `POST /login` | Página | `HX-Redirect` o partial con error |
| `POST /signup` | Página | `HX-Redirect` o partial con error |
| `POST /logout` | Página | `HX-Redirect: /login`, borra cookies de sesión |
| `GET /onboarding` | Página | HTML |
| `GET /onboarding/step/{n}` | Página | Partial HTML |
| `POST /onboarding/step/{n}` | Página | Partial HTML |
| `POST /onboarding/finish` | Página | `HX-Redirect: /chat` |
| `GET /chat` | Página | HTML |
| `GET /chat/session/{id}` | Página | Fragmento: mensajes de la sesión (swap directo en `#messages`) más actualización OOB de sidebar, status bar y composer |
| `GET /settings` | Página | HTML |
| `POST /settings` | Página | Partial de estado guardado |
| `POST /api/chat` | API | Partial de respuesta, panel HITL, o fragmento de error controlado |
| `POST /api/chat/stream` | API | `text/event-stream` (SSE): eventos `tick`, `message_html`, `error` |
| `POST /api/chat/confirm` | API | Partial de respuesta final tras `approve`/`reject`; valida que la tool pendiente pertenezca al usuario autenticado |
| `GET /api/sessions` | API | JSON de sesiones |
| `POST /api/sessions` | API | Fragmento: sesión nueva insertada en el sidebar (OOB) más reset de `#messages`/composer/status bar |
| `POST /api/sessions/{id}/clear` | API | String vacío |
| `POST /api/sessions/{id}/archive` | API | `HX-Redirect: /chat` (si archiva la sesión actual) o partial vacío para remover el item del sidebar |
| `POST /api/sessions/{id}/delete` | API | `HX-Redirect: /chat` (si elimina la sesión actual) o partial vacío para remover el item del sidebar |

`POST /api/chat/stream` es la ruta que usa la UI real (SSE, vía `fetch`, no HTMX). `POST
/api/chat` es una ruta equivalente sin streaming, con el mismo contrato de adjuntos y
selector de modelo, y el mismo manejo de errores: ante una falla del agente (timeout, error
del modelo), ambas rutas devuelven una respuesta controlada y legible en vez de un error de
servidor sin manejar. Ver `docs/implementation-summary.md` para el detalle de sesiones
(título automático, archivar, eliminar).

## 5) Catálogo de herramientas y política de riesgo

El catálogo (`app/tools/catalog.py`) + `TOOL_HANDLERS` (`app/tools/adapters.py`) es el
mecanismo central del producto para agregar cualquier funcionalidad nueva sin tocar el
runtime del grafo. Reglas:

- `low`: ejecución directa (igual queda registrada en `tool_calls` para auditoría).
- `medium`/`high`: confirmación humana obligatoria antes de ejecutar.
- Herramientas no registradas, o no habilitadas para el usuario, o no habilitadas
  globalmente vía feature flag: fail-closed, nunca se ejecutan.

Ver `docs/implementation-summary.md` para el catálogo concreto implementado hoy y el
mecanismo de tool-calling, y `docs/extending.md` / `docs/mcp-extension-example.md` para cómo
agregar una tool nueva.

## 6) Seguridad (principios del producto)

- Toda tool de riesgo medio/alto requiere confirmación humana antes de ejecutarse
  (`interrupt()` + `Command(resume=...)`), con estado que sobrevive a refresh porque vive en
  el checkpointer de Postgres, no en memoria de proceso.
- Solo el usuario dueño de la sesión asociada a una tool pendiente puede aprobarla o
  rechazarla.
- El contenido inyectado en el prompt (memoria recuperada, contexto de perfil) nunca se trata
  como instrucción del sistema.
- Feature flags fail-closed (ej. `FILE_TOOLS_ENABLED`) y confinamiento de filesystem para
  file tools.
- Secretos (claves de Supabase, OpenRouter, Langfuse, `SECRET_KEY`) nunca se exponen al
  cliente.

Ver `.cursor/.rules/security.mdc` para las reglas concretas y `docs/implementation-summary.md`
para el mecanismo de mitigación de prompt injection.

## 7) Contrato de variables de entorno

| Variable | Uso |
| --- | --- |
| `SUPABASE_URL` | URL del proyecto |
| `SUPABASE_ANON_KEY` | Cliente anon |
| `SUPABASE_SERVICE_ROLE_KEY` | Operaciones servidor |
| `DATABASE_URL` | Conexión directa Postgres para checkpointing |
| `OPENROUTER_API_KEY` | LLM/embeddings |
| `SECRET_KEY` | Firma de sesión |
| `FILE_TOOLS_ENABLED` | Habilita las file tools (`read_file`/`write_file`/`edit_file`), fail-closed |
| `FILE_TOOLS_ROOT` | Raíz de confinamiento de archivos |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Credenciales del callback de trazas |
| `LANGFUSE_HOST` | Host de Langfuse |
| `EVAL_USER_ID` | Usuario de `profiles` contra el cual corre `evals/run_faq_experiment.py` |
| `MCP_EXAMPLE_SERVER_URL` | Config del stub de referencia MCP (`mcp_example_ping`) |
| `ENVIRONMENT` | `development` o `production`; controla `secure`/`https_only` en cookies de sesión |
| `PROPERTIES_SUPABASE_URL` | URL de un proyecto Supabase separado, solo lectura, para búsqueda de propiedades (opcional; ver `migrations/properties_db/`) |
| `PROPERTIES_SUPABASE_ANON_KEY` | Anon key de ese mismo proyecto de propiedades (opcional; nunca service role) |
| `PROPERTIES_SUPABASE_SERVICE_ROLE_KEY` | Service role del proyecto de propiedades; solo usada por `scripts/backfill_property_embeddings.py` (proceso offline/manual, nunca por la app en el path de request de un usuario). Nunca importar desde `app/tools` o `app/agent` |

Sin `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
`OPENROUTER_API_KEY` o `SECRET_KEY` la aplicación no arranca. El resto activa funcionalidad
específica ya implementada (file tools, trazas, evaluaciones, el stub de MCP, cookies
seguras en producción). `PROPERTIES_SUPABASE_URL` / `PROPERTIES_SUPABASE_ANON_KEY` /
`PROPERTIES_SUPABASE_SERVICE_ROLE_KEY` son opcionales: si faltan, la app arranca igual y la
tool de búsqueda de propiedades queda deshabilitada mediante un error controlado.
