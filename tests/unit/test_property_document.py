import importlib.util
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "backfill_property_embeddings.py"
_spec = importlib.util.spec_from_file_location("backfill_property_embeddings", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
backfill_property_embeddings = importlib.util.module_from_spec(_spec)
sys.modules["backfill_property_embeddings"] = backfill_property_embeddings
_spec.loader.exec_module(backfill_property_embeddings)

build_property_document = backfill_property_embeddings.build_property_document
compute_content_hash = backfill_property_embeddings.compute_content_hash

FULL_ROW = {
    "property_type": "apartamento",
    "operation_type": "venta",
    "neighborhood": "El Peñón",
    "comuna": "Comuna 2",
    "bedrooms": 3,
    "bathrooms": 2,
    "parking_spots": 1,
    "area_m2": 85,
    "stratum": 5,
    "floor_number": 4,
    "description": "Hermoso apartamento con vista a la ciudad.",
}


def test_build_property_document_with_all_fields():
    document = build_property_document(FULL_ROW)

    assert document == (
        "apartamento en venta en El Peñón, Comuna 2, Cali. "
        "3 habitaciones, 2 baños, 1 parqueadero(s), 85 m², estrato 5, piso 4. "
        "Hermoso apartamento con vista a la ciudad."
    )


def test_build_property_document_omits_missing_fields_without_none_or_artifacts():
    row = {
        "property_type": None,
        "operation_type": "arriendo",
        "neighborhood": None,
        "comuna": None,
        "bedrooms": None,
        "bathrooms": 1,
        "parking_spots": None,
        "area_m2": None,
        "stratum": None,
        "floor_number": None,
        "description": None,
    }

    document = build_property_document(row)

    assert "None" not in document
    assert "  " not in document
    assert ", ." not in document
    assert " ," not in document
    assert document == "en arriendo en Cali. 1 baños."


def test_build_property_document_all_fields_missing_still_mentions_cali():
    row = {
        "property_type": None,
        "operation_type": None,
        "neighborhood": None,
        "comuna": None,
        "bedrooms": None,
        "bathrooms": None,
        "parking_spots": None,
        "area_m2": None,
        "stratum": None,
        "floor_number": None,
        "description": "",
    }

    document = build_property_document(row)

    assert document == "en Cali."
    assert "None" not in document


def test_build_property_document_blank_strings_treated_as_missing():
    row = {**FULL_ROW, "neighborhood": "   ", "description": "   "}

    document = build_property_document(row)

    assert "  " not in document
    assert document.startswith("apartamento en venta en Comuna 2, Cali.")
    assert document.endswith("piso 4.")


def test_build_property_document_truncates_long_description():
    long_description = "x" * 1000
    row = {**FULL_ROW, "description": long_description}

    document = build_property_document(row)

    assert document.endswith("x" * 600)
    assert "x" * 601 not in document


def test_build_property_document_missing_row_keys_treated_as_missing():
    document = build_property_document({"operation_type": "venta"})

    assert document == "en venta en Cali."


def test_compute_content_hash_is_deterministic_for_same_input():
    document = build_property_document(FULL_ROW)

    assert compute_content_hash(document) == compute_content_hash(document)


def test_compute_content_hash_differs_for_different_input():
    document_a = build_property_document(FULL_ROW)
    document_b = build_property_document({**FULL_ROW, "bedrooms": 4})

    assert compute_content_hash(document_a) != compute_content_hash(document_b)


def test_compute_content_hash_is_hex_sha256_digest():
    digest = compute_content_hash("cualquier texto")

    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)
