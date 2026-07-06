function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

// Debe reflejar el mismo texto/clases que la rama structured_payload.type ==
// "attachment_note" de app/templates/partials/message.html. Si cambia uno,
// cambiar el otro.
const ATTACHMENT_NOTE_CLASSES = "mt-1 text-xs opacity-80";

function attachmentNoteHtml(count) {
  return '<p class="' + ATTACHMENT_NOTE_CLASSES + '">📎 Se enviaron ' + count + " archivo(s)</p>";
}

const ATTACHMENT_LIMITS = {
  maxCount: 3,
  maxImageBytes: 5 * 1024 * 1024,
  imageTypes: ["image/png", "image/jpeg", "image/webp"],
};

let pendingAttachments = [];

function setAttachmentError(message) {
  const el = document.getElementById("attachment-error");
  if (!el) return;
  if (!message) {
    el.textContent = "";
    el.classList.add("hidden");
    return;
  }
  el.textContent = message;
  el.classList.remove("hidden");
}

function validateAttachment(file) {
  if (ATTACHMENT_LIMITS.imageTypes.includes(file.type)) {
    if (file.size > ATTACHMENT_LIMITS.maxImageBytes) {
      return "La imagen '" + file.name + "' supera el límite de 5 MB.";
    }
    return null;
  }
  return "Tipo de archivo no permitido: '" + file.name + "'. Solo imágenes (PNG, JPEG, WEBP).";
}

function syncAttachmentInput() {
  const input = document.getElementById("chat-attachments");
  if (!input) return;
  const dt = new DataTransfer();
  pendingAttachments.forEach((file) => dt.items.add(file));
  input.files = dt.files;
}

function renderAttachmentPreview() {
  const preview = document.getElementById("attachment-preview");
  if (!preview) return;
  if (pendingAttachments.length === 0) {
    preview.innerHTML = "";
    preview.classList.add("hidden");
    preview.classList.remove("flex");
    return;
  }
  preview.classList.remove("hidden");
  preview.classList.add("flex");
  preview.innerHTML = pendingAttachments
    .map(
      (file, index) =>
        '<span class="inline-flex items-center gap-1 rounded-full bg-neutral-200 px-2 py-0.5 text-xs dark:bg-neutral-700">' +
        escapeHtml(file.name) +
        ' <button type="button" onclick="removeAttachment(' +
        index +
        ')" class="text-neutral-500 hover:text-red-500">&times;</button></span>'
    )
    .join(" ");
}

function removeAttachment(index) {
  pendingAttachments.splice(index, 1);
  syncAttachmentInput();
  renderAttachmentPreview();
  setAttachmentError(null);
}

function addAttachments(files) {
  setAttachmentError(null);
  for (const file of files) {
    if (pendingAttachments.length >= ATTACHMENT_LIMITS.maxCount) {
      setAttachmentError("Máximo " + ATTACHMENT_LIMITS.maxCount + " adjuntos por mensaje.");
      break;
    }
    const error = validateAttachment(file);
    if (error) {
      setAttachmentError(error);
      continue;
    }
    pendingAttachments.push(file);
  }
  syncAttachmentInput();
  renderAttachmentPreview();
}

function handleAttachmentSelection(input) {
  const files = Array.from(input.files || []);
  pendingAttachments = [];
  addAttachments(files);
}

function handleChatPaste(event) {
  const items = event.clipboardData && event.clipboardData.items;
  if (!items) return;
  const imageFiles = [];
  for (const item of items) {
    if (item.kind === "file" && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) imageFiles.push(file);
    }
  }
  if (imageFiles.length === 0) return;
  event.preventDefault();
  addAttachments(imageFiles);
}

function resetAttachmentsUI() {
  pendingAttachments = [];
  syncAttachmentInput();
  renderAttachmentPreview();
  setAttachmentError(null);
}

function renderOutgoingMessage(form) {
  if (form.dataset.isSubmitting === "true") return;
  const input = document.getElementById("chat-input");
  const messages = document.getElementById("messages");
  const container = document.getElementById("messages-container");
  if (!input || !messages || !container) return;
  const text = (input.value || "").trim();
  const attachmentCount = pendingAttachments.length;
  if (!text && attachmentCount === 0) return;
  input.value = "";

  const emptyState = document.getElementById("messages-empty-state");
  if (emptyState) emptyState.remove();

  const thinkingId = "thinking-" + Date.now().toString();
  form.dataset.pendingThinkingId = thinkingId;
  form.dataset.isSubmitting = "true";

  const textHtml = text ? '<p class="whitespace-pre-wrap">' + escapeHtml(text) + "</p>" : "";
  const attachmentHtml = attachmentCount > 0 ? attachmentNoteHtml(attachmentCount) : "";

  const userHtml =
    '<div class="flex justify-end">' +
    '<div class="max-w-[80%] rounded-lg px-4 py-2.5 text-sm leading-relaxed bg-blue-600 text-white">' +
    textHtml + attachmentHtml +
    "</div></div>";

  const thinkingHtml =
    '<div id="' + thinkingId + '" class="flex justify-start">' +
    '<div class="rounded-lg bg-neutral-100 px-4 py-2.5 text-sm dark:bg-neutral-800">' +
    '<span class="animate-pulse" data-thinking-label>Pensando...</span>' +
    "</div></div>";

  messages.insertAdjacentHTML("beforeend", userHtml + thinkingHtml);
  container.scrollTop = container.scrollHeight;
}

function finishOutgoingMessage(form) {
  form.dataset.isSubmitting = "false";
  const thinkingId = form.dataset.pendingThinkingId;
  if (thinkingId) {
    const thinkingNode = document.getElementById(thinkingId);
    if (thinkingNode) thinkingNode.remove();
    delete form.dataset.pendingThinkingId;
  }
  const input = document.getElementById("chat-input");
  if (input) input.focus();
  const container = document.getElementById("messages-container");
  if (container) container.scrollTop = container.scrollHeight;
  refreshSessionSidebarItem(form);
}

// El titulo de sesion se genera en background en el servidor (puede tardar
// mas que un unico timeout fijo si la llamada al modelo es lenta). En vez de
// un solo intento a ciegas, reintentamos con backoff corto (1s/2s/3s) para
// darle mas chances de llegar antes de rendirse; en el peor caso, el sidebar
// igual se pone al dia en el proximo cambio de sesion o recarga de pagina.
const SESSION_TITLE_RETRY_DELAYS_MS = [1000, 2000, 3000];

function refreshSessionSidebarItem(form) {
  const sessionIdInput = form.querySelector('input[name="session_id"]');
  const sessionId = sessionIdInput && sessionIdInput.value;
  if (!sessionId) return;

  const attempt = (attemptIndex) => {
    setTimeout(async () => {
      try {
        const response = await fetch("/api/sessions/" + sessionId + "/item");
        if (!response.ok) return;
        const html = await response.text();
        const existing = document.getElementById("session-item-" + sessionId);
        if (existing) {
          existing.outerHTML = html;
          const updated = document.getElementById("session-item-" + sessionId);
          if (updated) htmx.process(updated);
        }
      } catch (_err) {
        // Best-effort refresh; sidebar will catch up on next session switch or page load.
      }
      if (attemptIndex + 1 < SESSION_TITLE_RETRY_DELAYS_MS.length) {
        attempt(attemptIndex + 1);
      }
    }, SESSION_TITLE_RETRY_DELAYS_MS[attemptIndex]);
  };

  attempt(0);
}

function guardChatSubmit(form) {
  if (form.dataset.isSubmitting === "true") return false;
  const input = document.getElementById("chat-input");
  const sessionIdInput = form.querySelector('input[name="session_id"]');
  if (!input || !sessionIdInput) return false;
  if (!(sessionIdInput.value || "").trim()) return false;
  const hasText = !!(input.value || "").trim();
  const hasAttachments = pendingAttachments.length > 0;
  if (!hasText && !hasAttachments) return false;
  return true;
}

const CODE_FENCE_RE = /```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g;

// Solo matchea links markdown `[texto](url)` cuya URL empieza EXACTAMENTE con
// "https://" (case-insensitive), sin espacios ni parentesis dentro de la URL. Cualquier
// otro esquema (http://, javascript:, data:, vbscript:, // protocol-relative, etc.) no
// matchea este regex y por lo tanto NUNCA se convierte a <a> -- queda como texto plano
// escapado, igual que el resto del mensaje.
const MARKDOWN_LINK_RE = /\[([^\]]+)\]\((https:\/\/[^\s)]+)\)/gi;

function renderTextWithLinks(text) {
  let html = "";
  let lastIndex = 0;
  let match;
  MARKDOWN_LINK_RE.lastIndex = 0;
  while ((match = MARKDOWN_LINK_RE.exec(text)) !== null) {
    const [full, linkText, url] = match;
    const before = text.slice(lastIndex, match.index);
    if (before) html += escapeHtml(before);
    // Defensa en profundidad: el charset de la URL ya esta acotado por el regex
    // (sin espacios/parentesis), pero igual se escapa antes de interpolar en el atributo.
    html +=
      '<a href="' + escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' +
      escapeHtml(linkText) +
      "</a>";
    lastIndex = match.index + full.length;
  }
  const rest = text.slice(lastIndex);
  if (rest) html += escapeHtml(rest);
  return html;
}

function renderAssistantContentHtml(rawText) {
  let html = "";
  let lastIndex = 0;
  let match;
  CODE_FENCE_RE.lastIndex = 0;
  while ((match = CODE_FENCE_RE.exec(rawText)) !== null) {
    const [full, lang, code] = match;
    const before = rawText.slice(lastIndex, match.index);
    if (before) html += renderTextWithLinks(before);
    const langClass = lang ? " language-" + escapeHtml(lang) : "";
    html +=
      '<div class="code-block group/code relative my-2">' +
      '<button type="button" data-copy-code title="Copiar código" ' +
      'class="absolute right-1 top-1 rounded bg-neutral-700/80 px-1.5 py-0.5 text-xs text-neutral-100 opacity-0 transition-opacity hover:bg-neutral-600 group-hover/code:opacity-100">📋</button>' +
      '<pre class="overflow-x-auto rounded-md p-3 text-xs"><code class="' +
      langClass.trim() +
      '">' +
      escapeHtml(code) +
      "</code></pre></div>";
    lastIndex = match.index + full.length;
  }
  const rest = rawText.slice(lastIndex);
  if (rest) html += renderTextWithLinks(rest);
  return html;
}

function enhanceAssistantMessage(el) {
  if (!el || el.dataset.hlProcessed === "true") return;
  const raw = el.dataset.rawContent;
  if (raw === undefined) return;
  el.innerHTML = renderAssistantContentHtml(raw);
  el.querySelectorAll("pre code").forEach((block) => hljs.highlightElement(block));
  el.dataset.hlProcessed = "true";
}

function enhanceAssistantMessages(root) {
  (root || document).querySelectorAll("[data-assistant-content]").forEach(enhanceAssistantMessage);
}

async function copyTextWithFeedback(text, button) {
  try {
    await navigator.clipboard.writeText(text || "");
  } catch (_err) {
    return;
  }
  const original = button.textContent;
  button.textContent = "Copiado ✓";
  setTimeout(() => {
    button.textContent = original;
  }, 2000);
}

document.addEventListener("click", (event) => {
  const copyMessageBtn = event.target.closest("[data-copy-message]");
  if (copyMessageBtn) {
    const bubble = copyMessageBtn.closest(".group");
    const contentEl = bubble && bubble.querySelector("[data-assistant-content]");
    copyTextWithFeedback(contentEl ? contentEl.dataset.rawContent : "", copyMessageBtn);
    return;
  }
  const copyCodeBtn = event.target.closest("[data-copy-code]");
  if (copyCodeBtn) {
    const codeEl = copyCodeBtn.closest(".code-block").querySelector("code");
    copyTextWithFeedback(codeEl ? codeEl.textContent : "", copyCodeBtn);
  }
});

document.body.addEventListener("htmx:afterSwap", (event) => {
  enhanceAssistantMessages(event.target);
});

function restoreSidebarFocus() {
  const firstItemButton = document.querySelector("#session-list [data-session-item] button");
  if (firstItemButton) {
    firstItemButton.focus();
    return;
  }
  const newSessionButton = document.querySelector('#sidebar button[hx-post="/api/sessions"]');
  if (newSessionButton) newSessionButton.focus();
}

const sidebarEl = document.getElementById("sidebar");
if (sidebarEl) {
  // Al archivar/eliminar la sesion activa desde el sidebar, el swap
  // outerHTML remueve el nodo que tenia el foco (el propio boton
  // "Archivar"/"Eliminar" clickeado) y el navegador lo devuelve a <body>,
  // dejando a un usuario de teclado sin referencia. Si eso pasa, movemos el
  // foco a un lugar razonable del sidebar.
  sidebarEl.addEventListener("htmx:afterSwap", () => {
    if (document.activeElement === document.body) {
      restoreSidebarFocus();
    }
  });
}

function toggleSessionMenu(id) {
  const menu = document.getElementById("session-menu-" + id);
  if (!menu) return;
  document.querySelectorAll('[id^="session-menu-"]').forEach((el) => {
    if (el !== menu) el.classList.add("hidden");
  });
  menu.classList.toggle("hidden");
}

// Debe reflejar el mismo texto/clases que ERROR_BUBBLE_CLASSES y
// DEFAULT_ASSISTANT_ERROR_MESSAGE en app/routers/chat.py (_error_fragment,
// usado por la ruta sin streaming). Si cambia uno, cambiar el otro.
const ERROR_BUBBLE_CLASSES =
  "max-w-[80%] rounded-lg bg-amber-100 px-4 py-2.5 text-sm text-amber-900 dark:bg-amber-900/40 dark:text-amber-100";
const DEFAULT_ASSISTANT_ERROR_MESSAGE = "No pude generar la respuesta. Intenta de nuevo.";

function appendAssistantError(message) {
  const messages = document.getElementById("messages");
  const container = document.getElementById("messages-container");
  if (!messages) return;
  const safe = escapeHtml(message || DEFAULT_ASSISTANT_ERROR_MESSAGE);
  const html =
    '<div class="flex justify-start">' +
    '<div class="' + ERROR_BUBBLE_CLASSES + '">' +
    safe +
    "</div></div>";
  messages.insertAdjacentHTML("beforeend", html);
  if (container) container.scrollTop = container.scrollHeight;
}

function getFormSessionId(form) {
  const input = form && form.querySelector('input[name="session_id"]');
  return input ? input.value : "";
}

async function submitChat(event, form) {
  event.preventDefault();
  if (!guardChatSubmit(form)) return false;
  const formData = new FormData(form);
  const submittedSessionId = getFormSessionId(form);
  renderOutgoingMessage(form);
  resetAttachmentsUI();

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      body: formData,
      headers: { Accept: "text/event-stream" },
    });
    if (!response.ok || !response.body) {
      appendAssistantError(DEFAULT_ASSISTANT_ERROR_MESSAGE);
      return false;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    const messages = document.getElementById("messages");
    const container = document.getElementById("messages-container");

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const block of parts) {
        const lines = block.split("\n");
        let eventName = "message";
        let payload = "";
        for (const line of lines) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          if (line.startsWith("data:")) payload += line.slice(5).trim();
        }
        if (!payload) continue;
        let data = {};
        try {
          data = JSON.parse(payload);
        } catch (_err) {
          data = {};
        }
        if (eventName === "tick") {
          const thinkingId = form.dataset.pendingThinkingId;
          if (!thinkingId) continue;
          const label = document.querySelector("#" + thinkingId + " [data-thinking-label]");
          if (label && data.elapsed_ms) {
            const sec = (Number(data.elapsed_ms) / 1000).toFixed(1);
            label.textContent = "Pensando... " + sec + "s";
          }
          continue;
        }
        if (eventName === "error") {
          appendAssistantError(data.message);
          continue;
        }
        if (eventName === "message_html") {
          if (!messages || !data.html) continue;
          // El usuario pudo haber cambiado de sesion en el sidebar mientras
          // esperaba esta respuesta (#chat-composer se reemplaza por OOB swap
          // en cada cambio de sesion, con un #chat-form nuevo). Si la sesion
          // activa ya no es la que origino este envio, el backend igual
          // persistio el turno (_finalize_turn) asi que se descarta el insert
          // en silencio: se vera al volver a esa sesion.
          if (getFormSessionId(document.getElementById("chat-form")) !== submittedSessionId) {
            continue;
          }
          messages.insertAdjacentHTML("beforeend", data.html);
          enhanceAssistantMessages(messages);
          if (container) container.scrollTop = container.scrollHeight;
        }
      }
    }
    return false;
  } catch (_err) {
    appendAssistantError(
      "Se perdió la conexión mientras se generaba la respuesta. Es posible que el mensaje ya se haya procesado: cambia de sesión o recarga la página para verlo."
    );
    return false;
  } finally {
    finishOutgoingMessage(form);
  }
}

enhanceAssistantMessages(document);
