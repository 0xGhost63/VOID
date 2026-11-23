"""Pluggable storage places: cloud, local folder, Google Drive, GitHub."""

from .base import Entry, StorageProvider, sha256_bytes, sha256_file, sha256_stream
from .cloud import CloudProvider
from .github import GitHubProvider
from .gdrive import GoogleDriveProvider
from .local import LocalProvider

__all__ = [
    "Entry",
    "StorageProvider",
    "sha256_bytes",
    "sha256_file",
    "sha256_stream",
    "CloudProvider",
    "GitHubProvider",
    "GoogleDriveProvider",
    "LocalProvider",
]
