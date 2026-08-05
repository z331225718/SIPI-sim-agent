from __future__ import annotations


class ArtifactStoreError(RuntimeError):
    """Base error for attempt artifact preparation and publication."""


class ArtifactIntegrityError(ArtifactStoreError):
    """A staged or materialized file does not match its artifact reference."""


class AttemptAlreadyExists(ArtifactStoreError):
    """The destination attempt directory already exists and must not be overwritten."""


class SuccessMarkerAlreadyExists(ArtifactStoreError):
    """A success marker already exists and must never be replaced."""


class SuccessMarkerRejected(ArtifactStoreError):
    """A non-successful attempt cannot receive a success marker."""
