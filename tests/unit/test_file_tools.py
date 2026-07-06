from types import SimpleNamespace

import pytest

from app.tools.file_tools import execute_read_file, execute_write_file


def _fake_settings(*, enabled: bool, allowed_root):
    return SimpleNamespace(is_file_tools_enabled=enabled, file_tools_allowed_root=allowed_root)


def test_execute_read_file_raises_permission_error_when_file_tools_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.tools.file_tools.get_settings",
        lambda: _fake_settings(enabled=False, allowed_root=tmp_path),
    )
    with pytest.raises(PermissionError, match="FILE_TOOLS_ENABLED"):
        execute_read_file("whatever.txt")


def test_execute_write_file_raises_permission_error_when_file_tools_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.tools.file_tools.get_settings",
        lambda: _fake_settings(enabled=False, allowed_root=tmp_path),
    )
    with pytest.raises(PermissionError, match="FILE_TOOLS_ENABLED"):
        execute_write_file("whatever.txt", "contenido")
    # Fail-closed de verdad: nada se escribe en disco.
    assert not (tmp_path / "whatever.txt").exists()


def test_execute_read_file_blocks_relative_path_traversal_outside_root(monkeypatch, tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("no deberias poder leer esto")
    monkeypatch.setattr(
        "app.tools.file_tools.get_settings",
        lambda: _fake_settings(enabled=True, allowed_root=sandbox),
    )
    with pytest.raises(PermissionError, match="outside FILE_TOOLS_ROOT"):
        execute_read_file("../secret.txt")


def test_execute_read_file_blocks_absolute_path_outside_root(monkeypatch, tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setattr(
        "app.tools.file_tools.get_settings",
        lambda: _fake_settings(enabled=True, allowed_root=sandbox),
    )
    with pytest.raises(PermissionError, match="outside FILE_TOOLS_ROOT"):
        execute_read_file("/etc/passwd")


def test_execute_write_file_blocks_relative_path_traversal_outside_root(monkeypatch, tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setattr(
        "app.tools.file_tools.get_settings",
        lambda: _fake_settings(enabled=True, allowed_root=sandbox),
    )
    with pytest.raises(PermissionError, match="outside FILE_TOOLS_ROOT"):
        execute_write_file("../escaped.txt", "contenido")
    # El path traversal se bloquea antes de escribir nada fuera del sandbox.
    assert not (tmp_path / "escaped.txt").exists()


def test_execute_read_file_happy_path_within_allowed_root(monkeypatch, tmp_path):
    (tmp_path / "note.txt").write_text("hola\nmundo", encoding="utf-8")
    monkeypatch.setattr(
        "app.tools.file_tools.get_settings",
        lambda: _fake_settings(enabled=True, allowed_root=tmp_path),
    )
    assert execute_read_file("note.txt") == "hola\nmundo"


def test_execute_write_file_happy_path_within_allowed_root(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.tools.file_tools.get_settings",
        lambda: _fake_settings(enabled=True, allowed_root=tmp_path),
    )
    result = execute_write_file("new.txt", "contenido")
    assert result == "ok"
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "contenido"
