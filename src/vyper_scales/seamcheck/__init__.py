"""Cross-contract seam coverage checker."""

from .analyzer import analyze
from .manifest import load_manifest

__all__ = ["analyze", "load_manifest"]
