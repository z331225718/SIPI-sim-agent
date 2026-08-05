"""M0-only external-CAS protocol prototype; not a public runtime API."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, build_opener
import os


class ArtifactPolicyError(RuntimeError): pass
class ArtifactIntegrityError(RuntimeError): pass
class ArtifactUnavailableOffline(RuntimeError): pass


@dataclass(frozen=True)
class Descriptor:
    artifact_id: str
    transport_sha256: str
    transport_size_bytes: int
    provider_id: str
    distribution_status: str
    authorization_evidence_ref: str | None

    def __post_init__(self) -> None:
        if len(self.transport_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.transport_sha256):
            raise ArtifactPolicyError("digest must be 64 lowercase hex characters")
        if self.transport_size_bytes < 0:
            raise ArtifactPolicyError("size must be non-negative")


def _cache_path(cache_root: Path, digest: str) -> Path:
    return cache_root / "sha256" / digest[:2] / digest / "blob"


def _verify(path: Path, descriptor: Descriptor) -> None:
    digest = sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            digest.update(block)
    if size != descriptor.transport_size_bytes or digest.hexdigest() != descriptor.transport_sha256:
        raise ArtifactIntegrityError("artifact size or SHA-256 mismatch")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _loopback_url(base: str, descriptor: Descriptor) -> str:
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.port is None:
        raise ArtifactPolicyError("M0 mock providers must use loopback HTTP")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ArtifactPolicyError("provider URL contains unsupported components")
    return f"{base.rstrip('/')}/v1/blobs/sha256/{descriptor.transport_sha256}"


def fetch(descriptor: Descriptor, *, cache_root: Path, providers: dict[str, str], offline: bool = False) -> Path:
    if descriptor.distribution_status not in {"authorized_private", "authorized_public"}:
        raise ArtifactPolicyError("artifact distribution status is not store-consumable")
    if not descriptor.authorization_evidence_ref:
        raise ArtifactPolicyError("authorization evidence is required")
    target = _cache_path(cache_root, descriptor.transport_sha256)
    if target.exists():
        _verify(target, descriptor)
        return target
    if offline:
        raise ArtifactUnavailableOffline("verified artifact is not in the local cache")
    base = providers.get(descriptor.provider_id)
    if not base:
        raise ArtifactPolicyError("provider is not allowlisted")
    url = _loopback_url(base, descriptor)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        try:
            response = build_opener(_NoRedirect()).open(url, timeout=10)
        except (HTTPError, URLError) as error:
            if isinstance(error, HTTPError):
                error.close()
            raise ArtifactIntegrityError("provider request failed") from error
        with response, NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            content_length = response.headers.get("Content-Length")
            if content_length is not None and content_length != str(descriptor.transport_size_bytes):
                raise ArtifactIntegrityError("provider Content-Length mismatch")
            size = 0
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > descriptor.transport_size_bytes:
                    raise ArtifactIntegrityError("provider response exceeds declared size")
                stream.write(block)
            stream.flush()
            os.fsync(stream.fileno())
        _verify(temporary, descriptor)
        os.replace(temporary, target)
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
