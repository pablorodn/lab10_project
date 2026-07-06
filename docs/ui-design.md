# UI Design - lab10_project (Jinja2 + HTMX)

> Contrato visual y de comportamiento de la UI SSR/HTMX de `lab10_project`.

## 1) Principios de UI

- SSR + HTMX, sin SPA.
- Las respuestas de interacción son partials HTML, fragmentos con `hx-swap-oob`, o
  `HX-Redirect`.
- La UI no ejecuta políticas de seguridad; solo invoca endpoints del backend.
- Estado de sesión y del flujo HITL siempre proviene de servidor.

## 2) Pantallas principales

- `GET /login`
- `GET /signup`
- `GET /onboarding` (wizard de 4 pasos)
- `GET /chat` (multi-sesión con sidebar)
- `GET /settings`

## 3) Topbar y navegación

- La topbar está montada en todas las pantallas autenticadas.
- `chat` y `settings` navegan por links normales (`<a href>`).
- `logout` usa `hx-post` y `HX-Redirect`.

## 4) Chat web

- Chat multi-sesión con sidebar.
- Envío de mensajes y render de respuestas vía streaming (SSE).
- Flujo de confirmación HITL en UI.
- Adjuntos multimodales en el formulario del chat.
- Selector de modelo por usuario (vive en `/settings`, ver §7).
- Botón copiar por mensaje del asistente y por cada bloque de código.
- Resaltado de sintaxis en bloques de código.
- `#messages` usa `aria-live="polite"` y `aria-atomic="false"`: los mensajes nuevos se
  anuncian a lectores de pantalla sin releer todo el historial en cada turno.

Toda la lógica de envío, adjuntos, streaming y realce de mensajes vive en
`app/static/js/chat.js` (JS plano, sin build step ni dependencias de bundling).

### Sidebar de sesiones

- La lista de sesiones se muestra de más reciente a más antigua con máximo 10 items.
- Cada item de `partials/session_item.html` muestra `session.title` si existe; fallback a
  `format_session_date` cuando `title` es `null`, y a "Nueva sesión" si tampoco hay fecha.
- Cada item incluye un menú de 3 puntos (`toggleSessionMenu(sessionId)`, en
  `app/static/js/chat.js`) con dos acciones:
  - `Archivar` (sin confirmación).
  - `Eliminar` (con `hx-confirm`: "¿Eliminar esta conversación? Esta acción no se puede
    deshacer.").
- Crear sesión, cambiar de sesión, archivar y eliminar actualizan el sidebar de forma
  incremental (swap fuera de banda sobre el/los item(s) afectados), sin volver a pedir ni
  re-renderizar la lista completa de sesiones.

## 5) HTMX en chat (contrato)

`chat.html` envía cada turno vía `fetch` a `POST /api/chat/stream` (`text/event-stream`, no
HTMX), leyendo eventos `tick`/`message_html`/`error` e insertando el HTML recibido en
`#messages` manualmente. `POST /api/chat` es una ruta equivalente sin streaming (mismo
contrato de texto, adjuntos y selector de modelo, mismo manejo de errores), mantenida por
contrato pero no invocada por la UI real. El resto de la tabla corresponde a interacciones
HTMX reales:

| Acción | Método + ruta | `hx-target` | `hx-swap` | Respuesta |
| --- | --- | --- | --- | --- |
| Enviar mensaje (UI real, no HTMX) | `POST /api/chat/stream` vía `fetch` (SSE) | `#messages` (insertado manualmente) | — | Eventos `tick`/`message_html`/`error` |
| Confirmar HITL | `POST /api/chat/confirm` | `#messages` | `beforeend` | Partial de mensaje final |
| Crear sesión | `POST /api/sessions` | `#messages` | `innerHTML` | Reset de mensajes/composer/status-bar; nuevo item de sesión insertado en el sidebar vía `hx-swap-oob="afterbegin:#session-list"`, item anterior actualizado (des-resaltado) vía `hx-swap-oob="true"`, y el estado vacío del sidebar removido vía `hx-swap-oob="delete"` cuando corresponde |
| Cambiar sesión | `GET /chat/session/{id}` | `#messages` | `innerHTML` | Mensajes de la nueva sesión; item nuevo resaltado y anterior des-resaltado vía `hx-swap-oob="true"` sobre cada `partials/session_item.html`; composer y status bar también se refrescan vía OOB |
| Limpiar sesión | `POST /api/sessions/{id}/clear` | `#messages` | `innerHTML` | Vacío |
| Archivar sesión | `POST /api/sessions/{id}/archive` + `hx-vals` con `current_session_id` | `closest [data-session-item]` | `outerHTML` | `HX-Redirect: /chat` si era la sesión actual; si no, partial vacío que remueve el item |
| Eliminar sesión | `POST /api/sessions/{id}/delete` + `hx-vals` con `current_session_id` + `hx-confirm` | `closest [data-session-item]` | `outerHTML` | `HX-Redirect: /chat` si era la sesión actual; si no, partial vacío que remueve el item |

## 6) Adjuntos multimodales (UI + HTMX)

Contrato del formulario:

- `input type="file"` con `accept="image/png,image/jpeg,image/webp"`.
- `enctype="multipart/form-data"` en `#chat-form`.
- Envío de texto + archivos en una sola request. La UI real usa `POST /api/chat/stream`;
  `POST /api/chat` soporta el mismo contrato de adjuntos como ruta equivalente sin streaming.
- Permite pegar imagen desde portapapeles (`paste` sobre el input/área de chat) y adjuntarla
  sin pasar por selector de archivos.

Validaciones UX:

- Error claro si el tipo no está permitido.
- Error claro si excede el tamaño máximo.
- Bloqueo de submit mientras se procesa.

Límites:

- Imagen: hasta 5 MB.
- Máximo 3 adjuntos por mensaje.
- Sin persistencia de archivos en servidor o base de datos.
- El mensaje de texto es opcional cuando el turno incluye adjuntos: se puede enviar solo
  adjuntos sin texto acompañante.

Soporte multimodal: imágenes, con soporte garantizado para ambos modelos de la lista curada.

Persistencia de contexto de adjuntos en historial:

- Cuando un mensaje de usuario incluye adjuntos, el backend guarda metadata no sensible en
  `agent_messages.structured_payload` (ej. `{type: "attachment_note", count: N, kinds: [...]}`)
  sin contenido del archivo.
- `partials/message.html` renderiza un indicador genérico en el historial (`📎 Se enviaron N
  archivo(s)`) que persiste tras recargar la sesión.

## 7) Selector de modelo

El selector vive únicamente en `/settings` (`app/templates/settings.html`); la barra de chat
no tiene un `<select>` propio. El formulario de chat envía cada turno sin campo `chat_model`,
y el backend resuelve contra `profiles.default_model` en ambas rutas de envío (`POST
/api/chat` y `POST /api/chat/stream`).

- Lista curada:
  - `google/gemini-2.5-flash`
  - `openai/gpt-4o-mini`

Reglas:

- El selector solo afecta `create_chat_model()`.
- El modelo de compactación es fijo y no seleccionable por usuario.
- Si algún caller manda `chat_model` (ej. un cliente distinto de la UI), el valor se valida
  server-side contra la lista curada; si no coincide, se ignora y se usa el default con
  warning log (sin error duro al usuario).

## 8) Mejoras de render de mensajes

### Botón copiar

- Botón "Copiar" en cada mensaje del asistente y en cada bloque de código individual.
- Copia el contenido textual del mensaje o del bloque, con feedback visual breve.

### Bloques de código con resaltado

- `highlight.js` vía CDN (`base.html`/`chat.html`).
- Se re-ejecuta tras cada swap HTMX relevante (`htmx:afterSwap`) y tras cada mensaje nuevo
  insertado por streaming, con un guard de idempotencia para no reprocesar un mismo mensaje
  dos veces.
- HTML limpio y compatible con modo oscuro.

## 9) Onboarding y settings

- Onboarding de 4 pasos.
- Settings como pantalla de configuración de perfil, agente, catálogo de herramientas
  habilitadas y selector de modelo por defecto.

## 10) Inventario de partials relevantes

- `partials/topbar.html`
- `partials/message.html`
- `partials/confirmation.html`
- `partials/session_item.html`
- `partials/session_status_bar.html`
- `partials/chat_composer.html`
- `partials/chat_session_switch.html`
- `partials/settings_save_status.html`

El error de adjuntos vive inline en `partials/chat_composer.html` (`#attachment-error`); el
menú de 3 puntos (Archivar/Eliminar) vive inline en `partials/session_item.html`
(`#session-menu-{{ session.id }}`); `partials/message.html` renderiza el indicador
`attachment_note` en mensajes de usuario con adjuntos.

## 11) HTMX para adjuntos y selector de modelo

| Acción | Método + ruta | `hx-target` | `hx-swap` | Resultado |
| --- | --- | --- | --- | --- |
| Enviar chat con adjuntos (UI real, no HTMX) | `POST /api/chat/stream` vía `fetch` (SSE) | `#messages` (insertado manualmente) | — | Mensaje enviado con contenido multimodal |
| Guardar modelo preferido | `POST /settings` | `#save-status` | `innerHTML` | Confirmación de guardado |
