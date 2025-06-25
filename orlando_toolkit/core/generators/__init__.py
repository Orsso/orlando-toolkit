from __future__ import annotations

"""Modules responsible for generating DITA XML fragments and other outputs."""

from .dita_builder import create_dita_table  # noqa: F401

__all__: list[str] = [
    "create_dita_table",
] 