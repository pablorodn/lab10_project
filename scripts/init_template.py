#!/usr/bin/env python3
"""Bootstrap: renombra los metadatos de proyecto de esta plantilla.

Uso:
    python scripts/init_template.py "mi-agente-custom"

Reemplaza el nombre/título del proyecto en pyproject.toml, package.json,
app/main.py (título de FastAPI) y README.md. NO toca la carpeta app/ ni
ningún import de Python -- esos son la estructura real del paquete, no
metadata de proyecto.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]*$")

# Valor original de esta plantilla: si pyproject.toml ya no tiene este name,
# asumimos que el script ya se corrió antes.
ORIGINAL_PACKAGE_NAME = "agent-personal"


class TemplateInitError(Exception):
    pass


def validate_name(raw_name: str) -> str:
    name = raw_name.strip()
    if not name:
        raise TemplateInitError("El nombre del proyecto no puede estar vacío.")
    if not NAME_PATTERN.match(name):
        raise TemplateInitError(
            "Nombre inválido: usá letras, números, espacios, guiones o guiones bajos, "
            "empezando por un caracter alfanumérico."
        )
    return name


def derive_kebab_case(name: str) -> str:
    kebab = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not kebab:
        raise TemplateInitError(f"No se pudo derivar un nombre kebab-case válido de '{name}'.")
    return kebab


def derive_title_case(name: str) -> str:
    words = [w for w in re.split(r"[-_\s]+", name) if w]
    if not words:
        raise TemplateInitError(f"No se pudo derivar un título legible de '{name}'.")
    return " ".join(word.capitalize() for word in words)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_if_changed(path: Path, original: str, updated: str) -> bool:
    if updated == original:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def current_package_name(root: Path) -> str | None:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return None
    match = re.search(r'^name\s*=\s*"([^"]*)"', _read(pyproject), flags=re.MULTILINE)
    return match.group(1) if match else None


def already_initialized(root: Path) -> bool:
    return current_package_name(root) not in (None, ORIGINAL_PACKAGE_NAME)


def update_pyproject(root: Path, *, kebab: str, title: str) -> bool:
    path = root / "pyproject.toml"
    original = _read(path)
    updated = re.sub(
        r'^name\s*=\s*"[^"]*"', f'name = "{kebab}"', original, count=1, flags=re.MULTILINE
    )
    updated = re.sub(
        r'^description\s*=\s*"[^"]*"',
        f'description = "{title} - agente conversacional sobre FastAPI + LangGraph + Supabase"',
        updated,
        count=1,
        flags=re.MULTILINE,
    )
    return _write_if_changed(path, original, updated)


def update_package_json(root: Path, *, kebab: str) -> bool:
    path = root / "package.json"
    if not path.exists():
        return False
    original = _read(path)
    updated = re.sub(
        r'"name"\s*:\s*"[^"]*"', f'"name": "{kebab}-js-tests"', original, count=1
    )
    return _write_if_changed(path, original, updated)


def update_main_py(root: Path, *, title: str) -> bool:
    path = root / "app" / "main.py"
    if not path.exists():
        return False
    original = _read(path)
    updated = re.sub(
        r'FastAPI\(title="[^"]*"', f'FastAPI(title="{title}"', original, count=1
    )
    return _write_if_changed(path, original, updated)


def update_readme(root: Path, *, title: str) -> bool:
    path = root / "README.md"
    if not path.exists():
        return False
    original = _read(path)
    lines = original.splitlines(keepends=True)
    if lines and lines[0].startswith("# "):
        lines[0] = f"# {title}\n"
    updated = "".join(lines)
    return _write_if_changed(path, original, updated)


def run(new_name: str, root: Path, *, confirm_fn=input) -> None:
    name = validate_name(new_name)
    kebab = derive_kebab_case(name)
    title = derive_title_case(name)

    if already_initialized(root):
        current = current_package_name(root)
        print(
            f"Este proyecto ya parece haber sido renombrado antes (pyproject.toml tiene "
            f"name = \"{current}\", no el valor original de la plantilla)."
        )
        answer = confirm_fn("¿Sobrescribir de todos modos con el nuevo nombre? [y/N]: ")
        if answer.strip().lower() not in ("y", "yes", "s", "si", "sí"):
            print("Cancelado. No se modificó ningún archivo.")
            return

    changed = []
    if update_pyproject(root, kebab=kebab, title=title):
        changed.append("pyproject.toml")
    if update_package_json(root, kebab=kebab):
        changed.append("package.json")
    if update_main_py(root, title=title):
        changed.append("app/main.py")
    if update_readme(root, title=title):
        changed.append("README.md")

    print(f"Nombre del proyecto actualizado a '{name}' (kebab-case: '{kebab}', título: '{title}').")
    if changed:
        print("Archivos modificados: " + ", ".join(changed))
    else:
        print("Ningún archivo cambió (¿ya estaba con este nombre?).")

    print()
    print("Próximos pasos:")
    print("  1. Revisá el diff antes de commitear: git diff")
    print(
        "  2. (Opcional, manual) Renombrar la carpeta raíz del repo: "
        f"cd .. && mv {root.name} {kebab} && cd {kebab}"
    )
    print("  3. (Opcional) Borrar este script una vez usado: rm scripts/init_template.py")


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Uso: python {argv[0] if argv else 'scripts/init_template.py'} \"nombre-del-proyecto\"")
        return 1
    try:
        run(argv[1], root=Path(__file__).resolve().parent.parent)
    except TemplateInitError as exc:
        print(f"Error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
