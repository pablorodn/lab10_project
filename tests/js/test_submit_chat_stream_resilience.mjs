// Verificacion empirica (Fase 4, Bloque B) de dos fixes de resiliencia en
// submitChat() de app/static/js/chat.js:
//
// 1) El loop `while (true) { await reader.read() }` no tenia try/catch: si la
//    conexion se cortaba a mitad de un stream, la promesa de reader.read()
//    rechazaba, submitChat nunca llegaba a finishOutgoingMessage(form), y
//    #chat-input quedaba con isSubmitting="true" para siempre (bloqueando
//    nuevos envios) mientras la burbuja "Pensando..." quedaba colgada. Este
//    test simula un reader.read() que rechaza a mitad de stream y verifica
//    que: se muestra un mensaje de error visible, y el form vuelve a quedar
//    habilitado (isSubmitting === "false") pase lo que pase.
//
// 2) submitChat insertaba la respuesta (message_html) en #messages sin
//    verificar si el usuario habia cambiado de sesion en el sidebar mientras
//    esperaba (el sidebar hace un OOB swap de #chat-composer, con un
//    #chat-form nuevo, en cada cambio de sesion). Este test simula ese
//    cambio de sesion a mitad de stream y verifica que la respuesta de la
//    sesion vieja NO se inserta en el DOM de la sesion nueva.
//
// Uso: node tests/js/test_submit_chat_stream_resilience.mjs

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { JSDOM } from "jsdom";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..", "..");
const chatJsPath = path.join(repoRoot, "app", "static", "js", "chat.js");
const inlineScript = readFileSync(chatJsPath, "utf8");

let failures = 0;

function fail(message) {
  console.error("FAIL: " + message);
  failures += 1;
}

function pass(message) {
  console.log("PASS: " + message);
}

function buildDom(sessionId) {
  const domHtml = `<!doctype html>
<html>
<body>
  <div id="messages-container">
    <div id="messages"></div>
  </div>
  <p id="attachment-error" class="hidden"></p>
  <div id="attachment-preview" class="hidden"></div>
  <form id="chat-form">
    <input type="hidden" name="session_id" value="${sessionId}" />
    <input type="file" id="chat-attachments" name="attachments" multiple />
    <input id="chat-input" name="message" type="text" />
    <button type="submit" id="send-btn">Enviar</button>
  </form>
  <script>${inlineScript}</script>
</body>
</html>`;
  const dom = new JSDOM(domHtml, { runScripts: "dangerously", url: "http://localhost/" });
  dom.window.DataTransfer = class DataTransfer {
    constructor() {
      this.items = { add: () => {} };
    }

    get files() {
      return dom.window.document.getElementById("chat-attachments").files;
    }
  };
  dom.window.htmx = { process: () => {} };
  return dom;
}

function sseChunk(eventName, data) {
  return new TextEncoder().encode(`event: ${eventName}\ndata: ${JSON.stringify(data)}\n\n`);
}

async function testConnectionDropMidStream() {
  const dom = buildDom("session-1");
  const { window } = dom;
  const form = window.document.getElementById("chat-form");
  const input = window.document.getElementById("chat-input");
  input.value = "hola";

  let readCall = 0;
  const reader = {
    read: async () => {
      readCall += 1;
      if (readCall === 1) {
        return { done: false, value: sseChunk("tick", { elapsed_ms: 100 }) };
      }
      throw new TypeError("network error");
    },
  };
  window.fetch = async () => ({ ok: true, body: { getReader: () => reader } });

  await window.submitChat({ preventDefault: () => {} }, form);

  const messagesHtml = window.document.getElementById("messages").innerHTML;
  if (!messagesHtml.includes("conexión") && !messagesHtml.includes("conexion")) {
    fail("se esperaba una burbuja de error mencionando la conexión perdida, no se encontró en #messages");
  } else {
    pass("al cortarse la conexión a mitad de stream, se muestra una burbuja de error visible");
  }

  if (form.dataset.isSubmitting !== "false") {
    fail(
      `se esperaba form.dataset.isSubmitting === "false" tras el corte de conexión, pero quedó en ${JSON.stringify(form.dataset.isSubmitting)} (el form quedaría bloqueado para nuevos envíos)`
    );
  } else {
    pass("form.dataset.isSubmitting se resetea a false incluso cuando el stream se corta con error");
  }

  dom.window.close();
}

async function testSessionSwitchMidStreamDiscardsInsert() {
  const dom = buildDom("session-1");
  const { window } = dom;
  const form = window.document.getElementById("chat-form");
  const input = window.document.getElementById("chat-input");
  input.value = "hola";

  let readCall = 0;
  const reader = {
    read: async () => {
      readCall += 1;
      if (readCall === 1) {
        // Simula que, mientras se esperaba la respuesta, el usuario cambio de
        // sesion en el sidebar: HTMX reemplaza #chat-composer (outerHTML) con
        // un nuevo #chat-form apuntando a otra sesion.
        const oldForm = window.document.getElementById("chat-form");
        const newForm = window.document.createElement("form");
        newForm.id = "chat-form";
        newForm.innerHTML = '<input type="hidden" name="session_id" value="session-2" />';
        oldForm.replaceWith(newForm);
        return { done: false, value: sseChunk("message_html", { html: '<div id="reply-from-session-1">deberia descartarse</div>' }) };
      }
      return { done: true, value: undefined };
    },
  };
  window.fetch = async () => ({ ok: true, body: { getReader: () => reader } });

  await window.submitChat({ preventDefault: () => {} }, form);

  const messagesHtml = window.document.getElementById("messages").innerHTML;
  if (messagesHtml.includes("reply-from-session-1")) {
    fail("la respuesta de la sesión vieja se insertó en el DOM de la sesión nueva (fuga entre sesiones)");
  } else {
    pass("si el usuario cambia de sesión mientras espera, la respuesta de la sesión anterior no se inserta en el DOM");
  }

  if (form.dataset.isSubmitting !== "false") {
    fail("se esperaba isSubmitting === \"false\" tras terminar el stream aunque el insert se haya descartado");
  } else {
    pass("isSubmitting vuelve a false aunque el insert de message_html se haya descartado por cambio de sesión");
  }

  dom.window.close();
}

async function run() {
  await testConnectionDropMidStream();
  await testSessionSwitchMidStreamDiscardsInsert();
  if (failures > 0) {
    console.error(`\n${failures} verificacion(es) fallaron.`);
    process.exitCode = 1;
  } else {
    console.log("\nTodas las verificaciones pasaron.");
  }
}

run();
