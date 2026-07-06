// Verificacion empirica (Fase 14) del fix de orden en submitChat() de app/static/js/chat.js:
// el bug consistia en que renderOutgoingMessage(form) limpiaba #chat-input ANTES de que
// new FormData(form) se construyera, por lo que el campo "message" llegaba vacio al backend.
// Desde la Fase 4 (Bloque A) el JS de chat vive en app/static/js/chat.js, servido como archivo
// estatico (antes estaba inline en app/templates/chat.html). Este script carga ese archivo real
// dentro de un DOM real (jsdom), reproduce el formulario real de chat.html, simula texto escrito
// por el usuario, invoca la funcion submitChat() real (sin reescribirla a mano) y verifica el
// contenido efectivo del FormData que se enviaria a fetch().
//
// Uso: node tests/js/test_submit_chat_formdata.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { JSDOM } from "jsdom";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");
const chatJsPath = path.join(repoRoot, "app", "static", "js", "chat.js");

const inlineScript = readFileSync(chatJsPath, "utf8");

// DOM minimo que reproduce la estructura real del formulario de chat.html
// (ids/names identicos a los del archivo real).
const domHtml = `<!doctype html>
<html>
<body>
  <div id="messages-container">
    <div id="messages"></div>
  </div>
  <p id="attachment-error" class="hidden"></p>
  <div id="attachment-preview" class="hidden"></div>
  <form id="chat-form">
    <input type="hidden" name="session_id" value="session-1" />
    <input type="file" id="chat-attachments" name="attachments" multiple />
    <select name="chat_model" id="chat-model-select"><option value="google/gemini-2.5-flash" selected>x</option></select>
    <input id="chat-input" name="message" type="text" />
    <button type="submit" id="send-btn">Enviar</button>
  </form>
  <script>${inlineScript}</script>
</body>
</html>`;

const dom = new JSDOM(domHtml, { runScripts: "dangerously", url: "http://localhost/" });
const { window } = dom;

// jsdom no implementa DataTransfer (usado por el script real solo para
// sincronizar el input de adjuntos tras el envio) y su HTMLInputElement.files
// exige una instancia real de FileList (sin constructor publico). Como este
// escenario no tiene adjuntos, devolvemos el FileList vacio ya existente del
// propio input de archivos como stand-in valido.
window.DataTransfer = class DataTransfer {
  constructor() {
    this.items = { add: () => {} };
  }

  get files() {
    return window.document.getElementById("chat-attachments").files;
  }
};

let capturedFormData = null;
window.fetch = (_url, options) => {
  capturedFormData = options.body;
  // Simula una respuesta no-OK para que submitChat() corte temprano sin
  // necesitar simular un ReadableStream de verdad.
  return Promise.resolve({ ok: false, body: null });
};

const form = window.document.getElementById("chat-form");
const input = window.document.getElementById("chat-input");

const typedText = "Hola, este es un mensaje real escrito por el usuario";
input.value = typedText;

const fakeEvent = { preventDefault: () => {} };

async function run() {
  if (typeof window.submitChat !== "function") {
    console.error("FAIL: submitChat no quedo expuesto como funcion global tras ejecutar el script");
    process.exitCode = 1;
    return;
  }

  await window.submitChat(fakeEvent, form);

  if (!capturedFormData) {
    console.error("FAIL: fetch() nunca fue invocado (submitChat no llego a construir/enviar FormData)");
    process.exitCode = 1;
    return;
  }

  const messageValue = capturedFormData.get("message");
  console.log("Valor real del campo 'message' en el FormData enviado:", JSON.stringify(messageValue));

  if (messageValue !== typedText) {
    console.error(
      `FAIL: se esperaba message=${JSON.stringify(typedText)} pero el FormData real contenia message=${JSON.stringify(messageValue)}`
    );
    process.exitCode = 1;
    return;
  }

  // Verificacion adicional: el input SI se limpia visualmente para el usuario
  // (feedback inmediato de renderOutgoingMessage), pero eso debe ocurrir
  // DESPUES de haber capturado el FormData, no antes.
  if (input.value !== "") {
    console.error("FAIL: se esperaba que #chat-input quedara vacio tras el envio (feedback visual), pero no lo esta");
    process.exitCode = 1;
    return;
  }

  console.log("PASS: el FormData real capturado en fetch() contiene el texto tipeado por el usuario, y #chat-input se limpia recien despues de capturarlo.");
}

run();
