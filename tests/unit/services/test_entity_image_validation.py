"""Unit tests for the manual-image upload validator (Feature 092, T012, FR-002).

Validation is by content signature (magic bytes), not by a declared filename/type, and a
10 MB cap is enforced. These tests use only synthetic byte payloads — no real image files
and no library content (Constitution VI).
"""

from __future__ import annotations

import pytest

from chronovista.services.image_validation import (
    MAX_IMAGE_BYTES,
    ImageRejectionReason,
    ImageValidationError,
    read_and_validate,
    validate_image_bytes,
)

_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64
_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
# RIFF (0..3) + 4-byte size + WEBP (8..11) + payload.
_WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBP" + b"VP8 " + b"\x00" * 64


class TestValidateImageBytes:
    def test_accepts_jpeg(self) -> None:
        assert validate_image_bytes(_JPEG) == "jpg"

    def test_accepts_png(self) -> None:
        assert validate_image_bytes(_PNG) == "png"

    def test_accepts_webp(self) -> None:
        assert validate_image_bytes(_WEBP) == "webp"

    def test_rejects_text_renamed_to_image(self) -> None:
        text = b"this is plainly not an image, just ASCII text pretending to be one"
        with pytest.raises(ImageValidationError) as exc:
            validate_image_bytes(text)
        assert exc.value.reason is ImageRejectionReason.UNRECOGNIZED_SIGNATURE

    def test_rejects_empty(self) -> None:
        with pytest.raises(ImageValidationError) as exc:
            validate_image_bytes(b"")
        assert exc.value.reason is ImageRejectionReason.EMPTY

    def test_rejects_oversized(self) -> None:
        oversized = _JPEG + b"\x00" * (MAX_IMAGE_BYTES + 1 - len(_JPEG))
        assert len(oversized) == MAX_IMAGE_BYTES + 1
        with pytest.raises(ImageValidationError) as exc:
            validate_image_bytes(oversized)
        assert exc.value.reason is ImageRejectionReason.TOO_LARGE

    def test_rejects_riff_without_webp(self) -> None:
        # A RIFF container that is not WebP (e.g. a WAV) must not pass as an image.
        riff_wav = b"RIFF" + b"\x24\x00\x00\x00" + b"WAVE" + b"\x00" * 64
        with pytest.raises(ImageValidationError) as exc:
            validate_image_bytes(riff_wav)
        assert exc.value.reason is ImageRejectionReason.UNRECOGNIZED_SIGNATURE


class TestReadAndValidateStream:
    def test_reads_and_validates_chunks(self) -> None:
        data, ext = read_and_validate([_PNG[:8], _PNG[8:]])
        assert ext == "png"
        assert data == _PNG

    def test_aborts_before_buffering_oversized(self) -> None:
        # Each chunk is under the cap; the accumulation crosses it. The reader must stop
        # as soon as the cap is exceeded rather than buffer the whole payload.
        chunk = b"\x00" * (1024 * 1024)
        chunks = [_JPEG] + [chunk] * 11  # > 10 MiB in total
        with pytest.raises(ImageValidationError) as exc:
            read_and_validate(chunks)
        assert exc.value.reason is ImageRejectionReason.TOO_LARGE
