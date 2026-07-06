import base64
from typing import Any

from fastapi import UploadFile
from langchain_core.messages.content import create_image_block

MAX_ATTACHMENTS_PER_MESSAGE = 3
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {"image/png", "image/jpeg", "image/webp"}


class AttachmentValidationError(Exception):
    """Raised when an uploaded attachment fails type/size/count validation."""


def real_attachments(files: list[UploadFile]) -> list[UploadFile]:
    """Filter out empty file slots submitted by the browser when no file was picked."""
    return [f for f in files if f.filename]


async def build_attachment_blocks(
    files: list[UploadFile],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate uploaded files and build LangChain standard multimodal content blocks.

    Returns a tuple of (content_blocks, kinds) where kinds is the ordered list of
    unique attachment kinds present (currently only "image").

    Raises AttachmentValidationError with a user-facing message on the first
    invalid file (wrong type, over size limit, or too many attachments).
    """
    if len(files) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise AttachmentValidationError(
            f"Máximo {MAX_ATTACHMENTS_PER_MESSAGE} adjuntos por mensaje."
        )

    blocks: list[dict[str, Any]] = []
    kinds: list[str] = []
    for file in files:
        content = await file.read()
        mime_type = file.content_type or ""
        if mime_type in ALLOWED_IMAGE_MIME_TYPES:
            if len(content) > MAX_IMAGE_SIZE_BYTES:
                raise AttachmentValidationError(
                    f"La imagen '{file.filename}' supera el límite de 5 MB."
                )
            encoded = base64.b64encode(content).decode("ascii")
            blocks.append(dict(create_image_block(base64=encoded, mime_type=mime_type)))
            if "image" not in kinds:
                kinds.append("image")
        else:
            raise AttachmentValidationError(
                f"Tipo de archivo no permitido: '{file.filename}'. "
                "Solo se aceptan imágenes (PNG, JPEG, WEBP)."
            )
    return blocks, kinds
