"""test_core — Unit tests for MemPalace core modules.

Tests cover palace, config, backends/base, backends/registry, version,
and dialect modules. No real backend required.

Wing: openclaw | Topic: mempalace | Updated: 2026-06-28
"""

import os
import re

import pytest


class TestPalace:
    """Tests for mempalace.palace — resolve_backend_name."""

    def test_resolve_backend_name_default(self):
        """Returns 'qdrant' when nothing configured."""
        from mempalace.palace import resolve_backend_name

        result = resolve_backend_name("/nonexistent")
        assert result == "qdrant"

    def test_resolve_backend_name_env(self):
        """Respects MEMPALACE_BACKEND env var."""
        os.environ["MEMPALACE_BACKEND"] = "pgvector"
        try:
            from mempalace.palace import resolve_backend_name

            result = resolve_backend_name("/nonexistent")
            assert result == "pgvector"
        finally:
            del os.environ["MEMPALACE_BACKEND"]


class TestConfig:
    """Tests for mempalace.config — default constants."""

    def test_default_backend(self):
        from mempalace.config import DEFAULT_BACKEND

        assert DEFAULT_BACKEND == "qdrant"

    def test_default_collection_name(self):
        from mempalace.config import DEFAULT_COLLECTION_NAME

        assert DEFAULT_COLLECTION_NAME == "mempalace_drawers"


class TestBackendBase:
    """Tests for mempalace.backends.base — error hierarchy and value objects."""

    def test_backend_error_hierarchy(self):
        from mempalace.backends.base import BackendError, PalaceNotFoundError

        assert issubclass(PalaceNotFoundError, BackendError)

    def test_palace_ref_immutable(self):
        from mempalace.backends.base import PalaceRef

        ref = PalaceRef(id="test", local_path="/tmp")
        assert ref.id == "test"
        assert ref.local_path == "/tmp"

        with pytest.raises(TypeError):
            ref["id"] = "changed"


class TestBackendRegistry:
    """Tests for mempalace.backends.registry — registration and discovery."""

    def test_get_backend_unknown(self):
        from mempalace.backends.registry import get_backend

        with pytest.raises(KeyError):
            get_backend("nonexistent_backend")

    def test_available_backends_includes_qdrant(self):
        from mempalace.backends.registry import available_backends

        names = available_backends()
        assert "qdrant" in names
        assert "chroma" not in names


class TestVersion:
    """Tests for mempalace.version — version consistency with pyproject.toml."""

    def test_version_consistency(self):
        from mempalace.version import __version__

        import os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as f:
                pyproject = f.read()
        match = re.search(r'version\s*=\s*"([^"]+)"', pyproject)
        assert match is not None
        assert match.group(1) == __version__


class TestDialect:
    """Tests for mempalace.dialect — emotion codes and compression API."""

    def test_emotion_codes_happy(self):
        from mempalace.dialect import EMOTION_CODES

        assert "joy" in EMOTION_CODES
        assert "fear" in EMOTION_CODES

    def test_dialect_compress_exists(self):
        """Dialect.compress is callable (the AAAK compression entry point)."""
        from mempalace.dialect import Dialect

        assert callable(Dialect.compress)


class TestMCPTools:
    """Tests for mempalace.mcp_tools."""

    def test_mcp_tools_module_has_30_tools(self):
        from mempalace.mcp_tools import TOOLS
        assert len(TOOLS) == 30

    def test_mcp_tools_tool_has_handler_and_schema(self):
        from mempalace.mcp_tools import TOOLS
        for name, tool in TOOLS.items():
            assert "description" in tool, f"{name} missing description"
            assert "input_schema" in tool, f"{name} missing input_schema"
            assert "handler" in tool, f"{name} missing handler"


class TestSearcher:
    """Tests for mempalace.searcher."""

    def test_hybrid_rank_empty(self):
        from mempalace.searcher import _hybrid_rank
        result = _hybrid_rank([], "test")
        assert result == []

    def test_hybrid_rank_with_results(self):
        from mempalace.searcher import _hybrid_rank
        results = [
            {"text": "test about MemPalace architecture", "similarity": 0.5},
            {"text": "something else entirely", "similarity": 0.3},
        ]
        ranked = _hybrid_rank(results, "test")
        assert len(ranked) > 0
        assert isinstance(ranked, list)

    def test_metric_for_collection_none(self):
        from mempalace.searcher import _metric_for_collection
        result = _metric_for_collection(None)
        assert isinstance(result, str)
        assert result in ("cosine", "l2", "dot", "cosine_prenormalized")


class TestPalace:
    """Tests for mempalace.palace."""

    def test_skip_dirs_are_set(self):
        from mempalace.palace import SKIP_DIRS
        assert ".git" in SKIP_DIRS
        assert "node_modules" in SKIP_DIRS
        assert "__pycache__" in SKIP_DIRS
