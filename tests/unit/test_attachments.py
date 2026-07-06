import io

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.services.attachments import (
    MAX_ATTACHMENTS_PER_MESSAGE,
    AttachmentValidationError,
    build_attachment_blocks,
    real_attachments,
)


def _upload_file(filename: str, content: bytes, content_type: str) -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


def test_real_attachments_filters_empty_file_slots():
    empty = _upload_file("", b"", "application/octet-stream")
    valid = _upload_file("photo.png", b"data", "image/png")

    assert real_attachments([empty, valid]) == [valid]


@pytest.mark.anyio
async def test_build_attachment_blocks_accepts_image():
    image = _upload_file("photo.png", b"\x89PNG\r\n", "image/png")

    blocks, kinds = await build_attachment_blocks([image])

    assert kinds == ["image"]
    assert len(blocks) == 1
    assert blocks[0]["type"] == "image"
    assert blocks[0]["mime_type"] == "image/png"


@pytest.mark.anyio
async def test_build_attachment_blocks_dedupes_kinds():
    image_one = _upload_file("a.png", b"data", "image/png")
    image_two = _upload_file("b.jpeg", b"data", "image/jpeg")

    _, kinds = await build_attachment_blocks([image_one, image_two])

    assert kinds == ["image"]


@pytest.mark.anyio
async def test_build_attachment_blocks_rejects_too_many_files():
    files = [_upload_file(f"{i}.png", b"data", "image/png") for i in range(MAX_ATTACHMENTS_PER_MESSAGE + 1)]

    with pytest.raises(AttachmentValidationError, match="Máximo"):
        await build_attachment_blocks(files)


@pytest.mark.anyio
async def test_build_attachment_blocks_rejects_oversized_image():
    oversized = _upload_file("big.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")

    with pytest.raises(AttachmentValidationError, match="5 MB"):
        await build_attachment_blocks([oversized])


@pytest.mark.anyio
async def test_build_attachment_blocks_rejects_pdf():
    pdf = _upload_file("doc.pdf", b"%PDF-1.4", "application/pdf")

    with pytest.raises(AttachmentValidationError, match="no permitido"):
        await build_attachment_blocks([pdf])


@pytest.mark.anyio
async def test_build_attachment_blocks_rejects_disallowed_mime_type():
    disallowed = _upload_file("archive.zip", b"data", "application/zip")

    with pytest.raises(AttachmentValidationError, match="no permitido"):
        await build_attachment_blocks([disallowed])
