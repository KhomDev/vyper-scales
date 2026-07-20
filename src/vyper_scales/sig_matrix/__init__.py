"""Signature compatibility matrix generation and result checking."""

from .matrix import generate_cases
from .policy import load_policy

__all__ = ["generate_cases", "load_policy"]
