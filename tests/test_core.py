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

        pyproject = open("H:/Develop/Memplace/pyproject.toml").read()
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
