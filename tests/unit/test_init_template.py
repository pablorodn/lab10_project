import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "init_template.py"
_spec = importlib.util.spec_from_file_location("init_template", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
init_template = importlib.util.module_from_spec(_spec)
sys.modules["init_template"] = init_template
_spec.loader.exec_module(init_template)


PYPROJECT_FIXTURE = '''[project]
name = "agent-personal"
version = "0.1.0"
description = "Agente Personal MVP con FastAPI + LangGraph + Supabase"
readme = "README.md"
requires-python = ">=3.11"
dependencies = []
'''

PACKAGE_JSON_FIXTURE = '''{
  "name": "agent_total-js-tests",
  "private": true,
  "version": "0.0.0",
  "scripts": {
    "test:js": "node tests/js/test_a.mjs"
  }
}
'''

MAIN_PY_FIXTURE = '''from fastapi import FastAPI

app = FastAPI(title="Agente Personal MVP", lifespan=lifespan)
'''

README_FIXTURE = '''# agent_total

Plantilla de agente conversacional.

## Requisitos previos
'''


def _write_fixtures(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_FIXTURE, encoding="utf-8")
    (tmp_path / "package.json").write_text(PACKAGE_JSON_FIXTURE, encoding="utf-8")
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "main.py").write_text(MAIN_PY_FIXTURE, encoding="utf-8")
    (tmp_path / "README.md").write_text(README_FIXTURE, encoding="utf-8")
    return tmp_path


# --- validate_name ---


def test_validate_name_rejects_empty_string():
    with pytest.raises(init_template.TemplateInitError):
        init_template.validate_name("   ")


def test_validate_name_rejects_leading_symbol():
    with pytest.raises(init_template.TemplateInitError):
        init_template.validate_name("-mi-agente")


def test_validate_name_accepts_reasonable_name():
    assert init_template.validate_name("  mi-agente-custom  ") == "mi-agente-custom"


# --- derive_kebab_case / derive_title_case ---


def test_derive_kebab_case_from_spaces_and_underscores():
    assert init_template.derive_kebab_case("Mi Agente Custom") == "mi-agente-custom"
    assert init_template.derive_kebab_case("mi_agente_custom") == "mi-agente-custom"


def test_derive_title_case_from_hyphens_and_underscores():
    assert init_template.derive_title_case("mi-agente-custom") == "Mi Agente Custom"
    assert init_template.derive_title_case("mi_agente_custom") == "Mi Agente Custom"


# --- update_* funciones individuales, contra fixtures en tmp_path ---


def test_update_pyproject_replaces_name_and_description(tmp_path):
    root = _write_fixtures(tmp_path)
    changed = init_template.update_pyproject(root, kebab="mi-agente-custom", title="Mi Agente Custom")
    assert changed is True
    content = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "mi-agente-custom"' in content
    assert "Mi Agente Custom" in content
    # El resto del archivo (version, dependencies, etc.) no debe tocarse.
    assert 'version = "0.1.0"' in content
    assert 'requires-python = ">=3.11"' in content


def test_update_package_json_replaces_only_name_field(tmp_path):
    root = _write_fixtures(tmp_path)
    changed = init_template.update_package_json(root, kebab="mi-agente-custom")
    assert changed is True
    content = (root / "package.json").read_text(encoding="utf-8")
    assert '"name": "mi-agente-custom-js-tests"' in content
    # El resto del package.json (scripts, private, version) no debe tocarse.
    assert '"private": true' in content
    assert "test:js" in content


def test_update_main_py_replaces_only_fastapi_title(tmp_path):
    root = _write_fixtures(tmp_path)
    changed = init_template.update_main_py(root, title="Mi Agente Custom")
    assert changed is True
    content = (root / "app" / "main.py").read_text(encoding="utf-8")
    assert 'title="Mi Agente Custom"' in content
    # lifespan= (u otro kwarg) no debe alterarse.
    assert "lifespan=lifespan" in content


def test_update_readme_replaces_only_first_line(tmp_path):
    root = _write_fixtures(tmp_path)
    changed = init_template.update_readme(root, title="Mi Agente Custom")
    assert changed is True
    lines = (root / "README.md").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Mi Agente Custom"
    # El resto del README no debe alterarse.
    assert "Plantilla de agente conversacional." in lines


# --- already_initialized / run() orquestador ---


def test_already_initialized_false_for_original_template_name(tmp_path):
    root = _write_fixtures(tmp_path)
    assert init_template.already_initialized(root) is False


def test_already_initialized_true_after_first_run(tmp_path):
    root = _write_fixtures(tmp_path)
    init_template.run("mi-agente-custom", root=root, confirm_fn=lambda _msg: "y")
    assert init_template.already_initialized(root) is True


def test_run_updates_all_four_files(tmp_path):
    root = _write_fixtures(tmp_path)
    init_template.run("mi-agente-custom", root=root, confirm_fn=lambda _msg: "y")

    assert 'name = "mi-agente-custom"' in (root / "pyproject.toml").read_text(encoding="utf-8")
    assert '"name": "mi-agente-custom-js-tests"' in (root / "package.json").read_text(encoding="utf-8")
    assert 'title="Mi Agente Custom"' in (root / "app" / "main.py").read_text(encoding="utf-8")
    assert (root / "README.md").read_text(encoding="utf-8").splitlines()[0] == "# Mi Agente Custom"


def test_run_asks_for_confirmation_when_already_initialized_and_respects_no(tmp_path):
    root = _write_fixtures(tmp_path)
    init_template.run("primer-nombre", root=root, confirm_fn=lambda _msg: "y")
    pyproject_after_first_run = (root / "pyproject.toml").read_text(encoding="utf-8")

    prompts: list[str] = []

    def _deny(msg: str) -> str:
        prompts.append(msg)
        return "n"

    init_template.run("segundo-nombre", root=root, confirm_fn=_deny)

    assert prompts, "Se esperaba que run() pidiera confirmación antes de sobreescribir"
    # Al responder "n", el archivo no debe haber cambiado respecto del primer run.
    assert (root / "pyproject.toml").read_text(encoding="utf-8") == pyproject_after_first_run
    assert 'name = "primer-nombre"' in pyproject_after_first_run


def test_run_overwrites_when_confirmation_is_yes(tmp_path):
    root = _write_fixtures(tmp_path)
    init_template.run("primer-nombre", root=root, confirm_fn=lambda _msg: "y")
    init_template.run("segundo-nombre", root=root, confirm_fn=lambda _msg: "y")

    content = (root / "pyproject.toml").read_text(encoding="utf-8")
    assert 'name = "segundo-nombre"' in content
    assert "primer-nombre" not in content
