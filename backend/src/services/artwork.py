"""Album cover artwork caching (PLAN §6).

On import, cover artwork is downloaded **once** into ``settings.covers_dir``
(compose volume ``covers_data``) as ``{album_id}.{ext}`` and later served by
``GET /api/albums/{id}/cover``. The extension comes from sniffing the actual
image bytes (magic numbers) — the remote server's ``Content-Type`` header is
treated as a hint only. Every failure path returns ``None``: artwork caching
must never fail an import or a response (the frontend falls back to the
remote ``cover_url``).
"""

import mimetypes
from pathlib import Path

import httpx

from ..config import settings
from ..version import USER_AGENT

# ~15 MB cap on downloaded artwork (issue #3 acceptance criteria).
MAX_COVER_BYTES = 15 * 1024 * 1024
DOWNLOAD_TIMEOUT = 20.0

# Media type we serve per stored extension.
_MEDIA_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "gif": "image/gif",
}


def sniff_image(data: bytes) -> tuple[str, str] | None:
    """Return ``(ext, media_type)`` from magic bytes, or ``None`` if the data
    is not one of the image formats we serve."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def media_type_for_name(filename: str) -> str:
    """Media type for a stored cover filename (``12.jpg`` → ``image/jpeg``)."""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext in _MEDIA_TYPES:
        return _MEDIA_TYPES[ext]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def store_cover_bytes(
    data: bytes,
    album_id: int,
    *,
    covers_dir: str | Path | None = None,
    max_bytes: int | None = MAX_COVER_BYTES,
) -> str | None:
    """Store raw cover bytes as ``{album_id}.{ext}`` inside the covers dir.

    Sniffs the bytes (uploads never trust the client's ``Content-Type``),
    deletes any previously stored cover file for this album first — its
    extension may differ, e.g. old ``12.jpg`` vs new ``12.png`` — writes the
    new file, and returns the stored relative filename (``"12.png"``).

    Returns ``None`` on **any** failure (non-image bytes, over ``max_bytes``,
    I/O error) so the router can map it to a friendly 400 and artwork never
    raises into a 500 — same ethos as ``download_cover``.
    """
    if max_bytes is not None and len(data) > max_bytes:
        return None
    sniffed = sniff_image(data)
    if sniffed is None:
        return None
    ext, _media_type = sniffed
    try:
        root = _covers_root(covers_dir)
        root.mkdir(parents=True, exist_ok=True)
        for old in root.glob(f"{album_id}.*"):
            if old.is_file():
                old.unlink()
        target = root / f"{album_id}.{ext}"
        target.write_bytes(data)
        return target.name
    except OSError:
        return None


def _covers_root(covers_dir: str | Path | None = None) -> Path:
    if covers_dir is not None:
        return Path(covers_dir)
    return Path(settings.covers_dir)


def resolve_cover_file(
    cover_path: str | None, covers_dir: str | Path | None = None
) -> Path | None:
    """Resolve a stored ``cover_path`` to a real file inside ``covers_dir``.

    Path-traversal safe: only bare filenames (no separators, no ``..``) that
    resolve within the covers root are returned; anything else — or a missing
    file — yields ``None`` (the caller turns that into a 404).
    """
    if not cover_path:
        return None
    if Path(cover_path).name != cover_path or cover_path in (".", ".."):
        return None
    try:
        root = _covers_root(covers_dir).resolve()
        candidate = (root / cover_path).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    if not candidate.is_relative_to(root):
        return None
    if not candidate.is_file():
        return None
    return candidate


def download_cover(
    url: str | None,
    album_id: int,
    *,
    covers_dir: str | Path | None = None,
    client: httpx.Client | None = None,
    max_bytes: int = MAX_COVER_BYTES,
) -> str | None:
    """Download ``url`` into the covers dir as ``{album_id}.{ext}``.

    Returns the stored filename (relative to the covers dir, e.g. ``"12.jpg"``)
    on success, or ``None`` on **any** failure (HTTP error, oversized body,
    non-image payload, I/O error) — callers never need to guard imports against
    artwork problems. Pass ``client`` (e.g. one built on
    ``httpx.MockTransport``) to keep tests offline.
    """
    if not url:
        return None
    owns_client = client is None
    if owns_client:
        client = httpx.Client(
            follow_redirects=True,
            timeout=DOWNLOAD_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
    try:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            # Reject obvious non-images early (error pages, JSON) so we don't
            # burn the byte cap; octet-stream and friends still get sniffed.
            if ctype.startswith("text/") or ctype in (
                "application/json",
                "application/xml",
            ):
                return None
            chunks: list[bytes] = []
            total = 0
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > max_bytes:
                    return None
                chunks.append(chunk)
        data = b"".join(chunks)
        sniffed = sniff_image(data)
        if sniffed is None:
            return None  # trust the bytes, not the server's headers
        ext, _media_type = sniffed
        root = _covers_root(covers_dir)
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{album_id}.{ext}"
        target.write_bytes(data)
        return target.name
    except (httpx.HTTPError, OSError, ValueError):
        return None
    finally:
        if owns_client:
            client.close()
