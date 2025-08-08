import os
from pathlib import Path

import pytest

pytest.importorskip("lxml")


def _max_depth_by_structure(map_root):
    """Compute maximum structural depth by traversing nesting (ignores data-level)."""
    if map_root is None:
        return 0
    def _depth(node, level):
        if node is None:
            return level
        max_d = level
        for child in list(node):
            tag = getattr(child, "tag", "")
            if tag in ("topicref", "topichead") or str(tag).endswith("topicref") or str(tag).endswith("topichead"):
                max_d = max(max_d, _depth(child, level + 1))
        return max_d
    return _depth(map_root, 0)


@pytest.mark.parametrize("depth", [2, 3, 5, 10])
def test_convert_and_prepare_respects_depth(tmp_path, depth):
    from orlando_toolkit.core.services.conversion_service import ConversionService

    # Pick an existing DOCX fixture
    repo_root = Path(__file__).resolve().parents[3]
    docx_path = repo_root / "tests" / "fixtures" / "complex_depth_9_v2.docx"
    assert docx_path.exists(), "DOCX fixture missing"

    svc = ConversionService()

    # Convert and then prepare with selected depth
    ctx = svc.convert(str(docx_path), metadata={"topic_depth": depth})

    # Precondition: conversion produced a map
    assert getattr(ctx, "ditamap_root", None) is not None, "No map after conversion"

    # Run prepare_package which applies unified merge+prune using topic_depth
    ctx2 = svc.prepare_package(ctx)

    # After preparation, no nodes beyond selected depth should remain
    # The algorithm merges children beyond the depth into parents and prunes empty
    # nodes, so the deepest remaining data-level should be <= depth.
    deepest = _max_depth_by_structure(ctx2.ditamap_root)
    assert deepest <= depth, f"Found nodes deeper than configured depth {depth}: {deepest}"

    # Additionally, ensure no structural sections exist empty at max depth
    from lxml import etree as ET  # type: ignore
    # No topichead should remain that has no descendant content-bearing topicref
    for th in ctx2.ditamap_root.xpath(".//topichead"):
        has_desc_topic = bool(th.xpath(".//topicref[@href]"))
        assert has_desc_topic, "Empty structural section should not remain after merge/prune"


def test_export_zip_matches_in_memory_structure(tmp_path):
    from orlando_toolkit.core.services.conversion_service import ConversionService

    repo_root = Path(__file__).resolve().parents[3]
    docx_path = repo_root / "tests" / "fixtures" / "complex_depth_9.docx"
    assert docx_path.exists(), "DOCX fixture missing"

    svc = ConversionService()
    depth = 4
    ctx = svc.convert(str(docx_path), metadata={"topic_depth": depth})
    ctx2 = svc.prepare_package(ctx)

    # Save to a folder and re-read the ditamap to compare structural limits
    out_zip = tmp_path / "out.zip"
    debug_dir = tmp_path / "unzipped"
    svc.write_package(ctx2, out_zip, debug_copy_dir=debug_dir)

    # Validate unzipped map depth
    ditamap_files = list((debug_dir / "DATA").glob("*.ditamap"))
    assert ditamap_files, "No ditamap in exported package"
    from lxml import etree as ET  # type: ignore
    map_el = ET.parse(str(ditamap_files[0])).getroot()
    deepest = _max_depth_by_structure(map_el)
    assert deepest <= depth, f"Exported map deeper than {depth}: {deepest}"

