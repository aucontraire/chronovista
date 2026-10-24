"""Upload validation for the manual entity image (Feature 092).

Validates an uploaded image by its **content signature** (magic bytes), not by a
declared content-type or filename extension — a mislabeled or fabricated file is
rejected before it can reach the portrait (research.md R4, FR-002). Stdlib only;
no imaging library, no new third-party dependency.

Accepted formats and their first-bytes signatures:

* JPEG — ``FF D8 FF``
* PNG  — ``89 50 4E 47 0D 0A 1A 0A``
* WebP — ``RIFF`` (bytes 0..3) + ``WEBP`` (bytes 8..11)

A 10 MB (binary) cap is enforced. The caller stores no partial file on rejection.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

MAX_IMAGE_BYTES: int = 10 * 1024 * 1024  # 10 MiB

_JPEG_MAGIC = b"\xff\xd8\xff"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_RIFF_MAGIC = b"RIFF"
_WEBP_MAGIC = b"WEBP"


class ImageRejectionReason(str, Enum):
    """Why an uploaded image was rejected."""

    EMPTY = "empty"
    TOO_LARGE = "too_large"
    UNRECOGNIZED_SIGNATURE = "unrecognized_signature"


class ImageValidationError(Exception):
    """Raised when an uploaded image fails validation.

    Carries a machine-readable :class:`ImageRejectionReason` so the route can map it
    to an RFC7807 ``422`` with a specific, user-facing detail message.
    """

    def __init__(self, reason: ImageRejectionReason, message: str) -> None:
        self.reason = reason
        self.message = message
        super().__init__(message)


def _resolve_extension(data: bytes) -> str | None:
    """Return the file extension for a recognized signature, else ``None``."""
    if data.startswith(_JPEG_MAGIC):
        return "jpg"
    if data.startswith(_PNG_MAGIC):
        return "png"
    if len(data) >= 12 and data[0:4] == _RIFF_MAGIC and data[8:12] == _WEBP_MAGIC:
        return "webp"
    return None


def validate_image_bytes(data: bytes) -> str:
    """Validate uploaded image bytes and return the resolved extension.

    Parameters
    ----------
    data : bytes
        The complete uploaded file contents.

    Returns
    -------
    str
        The resolved extension: ``'jpg'``, ``'png'`` or ``'webp'``.

    Raises
    ------
    ImageValidationError
        If the payload is empty, exceeds :data:`MAX_IMAGE_BYTES`, or does not match a
        supported image signature.
    """
    if not data:
        raise ImageValidationError(ImageRejectionReason.EMPTY, "uploaded file is empty")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageValidationError(
            ImageRejectionReason.TOO_LARGE,
            f"uploaded file exceeds the {MAX_IMAGE_BYTES} byte limit",
        )
    ext = _resolve_extension(data)
    if ext is None:
        raise ImageValidationError(
            ImageRejectionReason.UNRECOGNIZED_SIGNATURE,
            "uploaded file is not a recognized JPEG, PNG or WebP image",
        )
    return ext


def read_and_validate(chunks: Iterable[bytes]) -> tuple[bytes, str]:
    """Read an upload stream, enforcing the size cap while reading, then validate.

    Reads ``chunks`` incrementally and aborts with :class:`ImageValidationError`
    (reason :attr:`ImageRejectionReason.TOO_LARGE`) as soon as the accumulated size
    exceeds :data:`MAX_IMAGE_BYTES`, so an oversized upload is never fully buffered.

    Parameters
    ----------
    chunks : Iterable[bytes]
        Successive byte chunks of the uploaded file.

    Returns
    -------
    tuple[bytes, str]
        The validated bytes and the resolved extension.

    Raises
    ------
    ImageValidationError
        On an empty, oversized, or unrecognized upload.
    """
    buffer = bytearray()
    for chunk in chunks:
        buffer.extend(chunk)
        if len(buffer) > MAX_IMAGE_BYTES:
            raise ImageValidationError(
                ImageRejectionReason.TOO_LARGE,
                f"uploaded file exceeds the {MAX_IMAGE_BYTES} byte limit",
            )
    data = bytes(buffer)
    return data, validate_image_bytes(data)
