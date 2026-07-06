# Lab10 Project

Plantilla de agente conversacional genérico y extensible: chat web con memoria de largo
plazo, confirmación humana (HITL) para acciones riesgosas, y un punto de extensión de
herramientas por catálogo + adapter. Stack: FastAPI + LangGraph + Supabase + OpenRouter +
Langfuse, UI SSR en Jinja2/HTMX.

## Usar esta plantilla

Este repo es una plantilla reutilizable de agente conversacional, pensada para arrancar un
proyecto nuevo a partir de ella.

1. Cloná el repo en una carpeta con el nombre de tu proyecto:
   ```bash
   git clone https://github.com/pablorodn/agent_personal.git nombre-de-tu-proyecto
   cd nombre-de-tu-proyecto
   ```
2. Renombrá los metadatos del proyecto (`pyproject.toml`, `package.json`, título de FastAPI,
   encabezado de este README):
   ```bash
   python scripts/init_template.py "nombre-de-tu-proyecto"
   ```
3. Seguí con el resto de este README normalmente (Requisitos previos, Instalación, etc.).

## Requisitos previos

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) para gestionar el entorno y las dependencias
- Node.js (para correr los tests de `tests/js/`)
- Una cuenta/proyecto de [Supabase](https://supabase.com) (Postgres + Auth)
- Una cuenta de [OpenRouter](https://openrouter.ai) (acceso a los modelos de chat)

## Instalación

```bash
git clone https://github.com/pablorodn/agent_personal.git
cd agent_total
uv sync --extra dev
npm install
```

`--extra dev` instala pytest, ruff y mypy además de las dependencias de la app. Si además
querés correr `scripts/check_connections.py` (verificación manual de conectividad), agregá
`--extra scripts` (usa `asyncpg`, no requerido por la app en sí):

```bash
uv sync --extra dev --extra scripts
```

## Configuración

Copiá `.env.example` a `.env` y completá las variables:

```bash
cp .env.example .env
```

| Variable | Uso |
| --- | --- |
| `SUPABASE_URL` | URL del proyecto Supabase |
| `SUPABASE_ANON_KEY` | Cliente anon de Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Cliente de service-role, usado por el backend |
| `DATABASE_URL` | Conexión directa a Postgres (checkpointing de LangGraph) |
| `OPENROUTER_API_KEY` | Acceso a los modelos de chat/embeddings vía OpenRouter |
| `SECRET_KEY` | Firma de la sesión HTTP (mínimo 32 caracteres) |
| `FILE_TOOLS_ENABLED` | `true`/`false`; habilita las tools `read_file`/`write_file`/`edit_file` (fail-closed si falta o es ambiguo) |
| `FILE_TOOLS_ROOT` | Raíz de confinamiento de archivos para las file tools |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Credenciales de trazas (opcional) |
| `LANGFUSE_HOST` | Host de Langfuse (opcional, default `https://cloud.langfuse.com`) |
| `EVAL_USER_ID` | UUID de un `profiles.id` existente, usado por `evals/run_faq_experiment.py` |
| `MCP_EXAMPLE_SERVER_URL` | Config ilustrativa del stub de referencia MCP (opcional) |
| `ENVIRONMENT` | `development` (default) o `production`; controla `secure`/`https_only` en cookies |

Sin `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
`OPENROUTER_API_KEY` o `SECRET_KEY` la aplicación no arranca.

**Cuidado**: si `.env` apunta a un proyecto Supabase real (no uno de prueba), cualquier
interacción con la app (login, mensajes de chat, etc.) escribe datos reales ahí.

## Base de datos

El esquema vive en `migrations/*.sql`, numeradas secuencialmente. No hay un runner
automatizado en el repo: aplicá cada archivo, en orden, contra tu proyecto Supabase — por
ejemplo desde el SQL Editor del dashboard de Supabase, o vía `psql`:

```bash
for f in migrations/*.sql; do psql "$DATABASE_URL" -f "$f"; done
```

Nunca modifiques una migración ya aplicada; los cambios de esquema posteriores van en un
archivo nuevo (`.cursor/.rules/guardrails.mdc`).

## Correr el servidor de desarrollo

```bash
uv run uvicorn app.main:app --port 8000 --host 127.0.0.1
```

No hay endpoint `/health`; usá `GET /login` (público, `200` cuando el server ya arrancó) para
chequear que está arriba. El log de arranque exitoso muestra `"event": "runtime_warmup"`
seguido de `Application startup complete.`; si en cambio aparece `runtime_warmup_failed`, el
pool del checkpointer no pudo conectar a `DATABASE_URL`.

## Tests

```bash
pytest tests/unit tests/integration tests/e2e
npm run test:js
```

## Lint y tipos

```bash
ruff check .
mypy app/
```

## Estructura del proyecto

```
app/routers/     rutas HTTP de API (chat, sesiones, auth)
app/pages/       rutas HTTP que renderizan páginas completas (chat, onboarding, settings)
app/agent/       runtime de LangGraph: grafo, checkpointer, compactación, memoria, modelo
app/tools/       catálogo de herramientas, schemas y handlers (adapters)
app/db/          acceso a Supabase y queries por tabla
app/services/    servicios transversales (HITL, adjuntos, política de memoria, onboarding)
app/middleware/  autenticación de requests
app/templates/   templates Jinja2 (páginas y partials HTMX)
app/static/js/   JS plano del cliente de chat (sin build step)
migrations/      esquema de Postgres, incremental
tests/           unit, integration, e2e (pytest) y tests/js (Node + jsdom)
evals/           evaluación del agente real contra casos de FAQ
scripts/         utilidades manuales (verificación de conectividad)
docs/            documentación de arquitectura y contrato de producto
```

## Documentación

| Documento | Qué describe |
| --- | --- |
| `docs/technical-brief.md` | Brief de producto: qué es `lab10_project` y qué hace |
| `docs/ui-design.md` | Contrato visual y HTMX de la UI |
| `docs/implementation-summary.md` | Cómo está construido en la práctica (mecanismos internos) |
| `docs/extending.md` | Guía para agregar herramientas o integraciones nuevas |
| `docs/mcp-extension-example.md` | Ejemplo de referencia del punto de extensión MCP |
| `migrations/*.sql` | Modelo de datos, fuente de verdad del esquema |
| `.cursor/.rules/*.mdc` | Reglas de arquitectura, seguridad, testing y colaboración |
