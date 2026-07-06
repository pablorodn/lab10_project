// Verificacion de renderTextWithLinks()/renderAssistantContentHtml() en
// app/static/js/chat.js: la tool search_properties devuelve markdown plano
// `[texto](url)` para los links de cada propiedad (nunca HTML), y el usuario
// espera verlos como <a> clickeables en vez de texto plano con corchetes.
//
// Reglas verificadas:
// - Solo se convierte a <a> un link markdown cuya URL empieza EXACTAMENTE con
//   "https://" (case-insensitive). Cualquier otro esquema (http://,
//   javascript:, data:, etc.) se deja como texto plano escapado -- nunca un
//   link roto a medias.
// - target="_blank" y rel="noopener noreferrer" son fijos y estaticos.
// - El contenido dentro de un fence de codigo (``` ```) nunca se toca aunque
//   contenga sintaxis de link markdown escrita literalmente.
//
// Uso: node tests/js/test_render_assistant_links.mjs

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

function assertEqual(actual, expected, message) {
  if (actual === expected) {
    pass(message);
  } else {
    fail(message + `\n  esperado: ${JSON.stringify(expected)}\n  obtenido: ${JSON.stringify(actual)}`);
  }
}

function assertIncludes(haystack, needle, message) {
  if (haystack.includes(needle)) {
    pass(message);
  } else {
    fail(message + `\n  no se encontro: ${JSON.stringify(needle)}\n  en: ${JSON.stringify(haystack)}`);
  }
}

function assertNotIncludes(haystack, needle, message) {
  if (!haystack.includes(needle)) {
    pass(message);
  } else {
    fail(message + `\n  se encontro (no deberia): ${JSON.stringify(needle)}\n  en: ${JSON.stringify(haystack)}`);
  }
}

function buildDom() {
  const domHtml = `<!doctype html>
<html>
<body></body>
</html>`;
  const dom = new JSDOM(domHtml, { runScripts: "dangerously", url: "http://localhost/" });
  return dom;
}

function run() {
  const dom = buildDom();
  const { window } = dom;
  const script = window.document.createElement("script");
  script.textContent = inlineScript;
  window.document.body.appendChild(script);

  const { renderAssistantContentHtml, escapeHtml } = window;

  // 1) Texto plano sin links: identico al comportamiento de siempre (escapeHtml puro).
  {
    const text = 'Precio: $100 & sin links aquí, ni <script>.';
    const actual = renderAssistantContentHtml(text);
    assertEqual(actual, escapeHtml(text), "texto plano sin links se escapa igual que antes");
  }

  // 2) Un link markdown simple.
  {
    const text = "Mira esto: [Ver publicación](https://example.com/x) y avisame.";
    const actual = renderAssistantContentHtml(text);
    const expected =
      escapeHtml("Mira esto: ") +
      '<a href="https://example.com/x" target="_blank" rel="noopener noreferrer">Ver publicación</a>' +
      escapeHtml(" y avisame.");
    assertEqual(actual, expected, "un link markdown simple se convierte a <a> con target/rel fijos");
  }

  // 3) Multiples links en el mismo texto; texto entre ellos preservado y escapado.
  {
    const text = "Primero [A](https://a.com/1) & luego [B](https://b.com/2) listo.";
    const actual = renderAssistantContentHtml(text);
    assertIncludes(
      actual,
      '<a href="https://a.com/1" target="_blank" rel="noopener noreferrer">A</a>',
      "múltiples links: el primero se convierte a <a>"
    );
    assertIncludes(
      actual,
      '<a href="https://b.com/2" target="_blank" rel="noopener noreferrer">B</a>',
      "múltiples links: el segundo se convierte a <a>"
    );
    assertIncludes(actual, "&amp; luego", "múltiples links: el texto entre ambos queda escapado");
  }

  // 4) Intento malicioso con esquema javascript: no debe producir ningun <a>.
  {
    const text = "[click](javascript:alert(1))";
    const actual = renderAssistantContentHtml(text);
    assertNotIncludes(actual, "<a", "esquema javascript: nunca produce un <a>");
    assertEqual(
      actual,
      escapeHtml(text),
      "esquema javascript: el texto literal del intento de link queda como texto plano escapado"
    );
  }

  // 5) URL con esquema http:// (no https): mismo trato, texto plano.
  {
    const text = "[link](http://example.com/x)";
    const actual = renderAssistantContentHtml(text);
    assertNotIncludes(actual, "<a", "esquema http:// (no https) nunca produce un <a>");
    assertEqual(
      actual,
      escapeHtml(text),
      "esquema http:// (no https) queda como texto plano escapado"
    );
  }

  // 6) Link markdown escrito DENTRO de un fence de codigo: sigue siendo codigo plano.
  {
    const text = "```\n[Ver publicación](https://example.com/x)\n```";
    const actual = renderAssistantContentHtml(text);
    assertIncludes(actual, "<pre", "un link markdown dentro de un fence sigue generando <pre><code>");
    assertIncludes(actual, "<code", "un link markdown dentro de un fence sigue generando <pre><code>");
    assertNotIncludes(
      actual,
      '<a href="https://example.com/x"',
      "un link markdown dentro de un fence de código NUNCA se convierte a <a>"
    );
    assertIncludes(
      actual,
      escapeHtml("[Ver publicación](https://example.com/x)"),
      "el texto literal del link markdown se preserva escapado dentro del bloque de código"
    );
  }

  // 7) Code fence Y link markdown fuera del fence en el mismo mensaje.
  {
    const text =
      "Antes [Ver más](https://example.com/y) del código:\n```python\nprint(1)\n```\nDespués nada.";
    const actual = renderAssistantContentHtml(text);
    assertIncludes(
      actual,
      '<a href="https://example.com/y" target="_blank" rel="noopener noreferrer">Ver más</a>',
      "el link fuera del fence se convierte a <a> aunque el mensaje también tenga un code fence"
    );
    assertIncludes(actual, "language-python", "el code fence se sigue procesando con su clase de lenguaje");
    assertIncludes(actual, "print(1)", "el contenido del code fence se preserva");
    assertIncludes(
      actual,
      escapeHtml("Después nada."),
      "el texto después del fence se sigue escapando normalmente"
    );
    assertNotIncludes(actual, "<a href=\"https://example.com/y\" target=\"_blank\" rel=\"noopener noreferrer\">print", "el <a> no se filtra dentro del bloque de código");
  }

  // 8) Texto del link con caracteres que necesitan escape.
  {
    const text = '[A & <B> "C"](https://example.com/z)';
    const actual = renderAssistantContentHtml(text);
    assertIncludes(
      actual,
      '<a href="https://example.com/z" target="_blank" rel="noopener noreferrer">A &amp; &lt;B&gt; &quot;C&quot;</a>',
      "el texto del link con caracteres especiales aparece correctamente escapado dentro del <a>"
    );
  }

  dom.window.close();

  if (failures > 0) {
    console.error(`\n${failures} verificacion(es) fallaron.`);
    process.exitCode = 1;
  } else {
    console.log("\nTodas las verificaciones pasaron.");
  }
}

run();
