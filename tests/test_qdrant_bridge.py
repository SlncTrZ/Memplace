"""Backend abstraction layer tests for MemPalace (RFC 001).

Tests the registry, in-tree backends (chroma, qdrant, pgvector, sqlite_exact),
error classes, and value objects — all via unit tests with mocks.

No real Qdrant/Ollama/chromadb server required.

Wing: openclaw | Topic: mempalace | Updated: 2026-06-28
"""

from unittest.mock import MagicMock, patch

import pytest

# Base imports shared across test classes
from mempalace.backends.base import (
    BackendClosedError,
    BackendError,
    BackendMismatchError,
    BaseBackend,
    BaseCollection,
    CollectionNotInitializedError,
    DimensionMismatchError,
    EmbedderIdentityMismatchError,
    GetResult,
    HealthStatus,
    LexicalHit,
    LexicalResult,
    MaintenanceResult,
    PalaceNotFoundError,
    PalaceRef,
    QueryResult,
    UnsupportedCapabilityError,
    UnsupportedFilterError,
    UnsupportedMaintenanceKindError,
    EmbedderIdentity,
    check_embedder_identity,
)
from mempalace.backends.registry import (
    available_backends,
    get_backend,
    get_backend_class,
    register,
    reset_backends,
    resolve_backend_for_palace,
    unregister,
)


# ---------------------------------------------------------------------------
# Helpers — concrete stubs for default-method tests
# ---------------------------------------------------------------------------


class _ConcreteCollection(BaseCollection):
    """Minimal concrete subclass for testing BaseCollection default methods."""

    def add(self, *, documents, ids, metadatas=None, embeddings=None):
        pass

    def upsert(self, *, documents, ids, metadatas=None, embeddings=None):
        pass

    def query(
        self,
        *,
        query_texts=None,
        query_embeddings=None,
        n_results=10,
        where=None,
        where_document=None,
        include=None,
    ) -> QueryResult:
        return QueryResult.empty()

    def get(
        self,
        *,
        ids=None,
        where=None,
        where_document=None,
        limit=None,
        offset=None,
        include=None,
    ) -> GetResult:
        return GetResult.empty()

    def delete(self, *, ids=None, where=None):
        pass

    def count(self) -> int:
        return 0


class _ConcreteBackend(BaseBackend):
    """Minimal concrete subclass for testing BaseBackend default methods."""

    name = "concrete_test"

    def get_collection(self, *args, **kwargs) -> BaseCollection:
        return _ConcreteCollection()


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestBackendRegistry:
    """Test backend registry: discovery, singleton instances, resolution."""

    def test_available_backends(self):
        """available_backends() returns the four in-tree backends sorted."""
        reset_backends()
        names = available_backends()
        assert names == ["chroma", "pgvector", "qdrant", "sqlite_exact"]

    def test_get_backend_returns_singleton(self):
        """get_backend('chroma') returns a cached singleton instance."""
        reset_backends()
        inst1 = get_backend("chroma")
        inst2 = get_backend("chroma")
        assert inst1 is inst2

    def test_get_backend_unknown_raises_keyerror(self):
        """get_backend('nonexistent') raises KeyError."""
        with pytest.raises(KeyError, match="unknown backend|nonexistent"):
            get_backend("nonexistent")

    def test_register_and_unregister(self):
        """register/unregister adds/removes a backend dynamically."""

        class FakeBackend(BaseBackend):
            name = "fake_test"

            def get_collection(self, *args, **kwargs):
                return _ConcreteCollection()

        register("fake_test", FakeBackend)
        assert "fake_test" in available_backends()

        inst = get_backend("fake_test")
        assert isinstance(inst, FakeBackend)

        unregister("fake_test")
        assert "fake_test" not in available_backends()

    def test_register_overrides_discovered(self):
        """Explicit register() wins over built-in entry point."""
        reset_backends()

        class OverrideChroma(BaseBackend):
            name = "chroma_override"

            def get_collection(self, *args, **kwargs):
                return _ConcreteCollection()

        register("chroma", OverrideChroma)
        inst = get_backend("chroma")
        assert isinstance(inst, OverrideChroma)

        # Restore original chroma backend so subsequent tests are not poisoned.
        from mempalace.backends.chroma import ChromaBackend

        register("chroma", ChromaBackend)
        reset_backends()

    def test_resolve_backend_picks_explicit_first(self):
        """resolve_backend_for_palace picks explicit > config > env > detect > default."""
        result = resolve_backend_for_palace(
            explicit="qdrant",
            config_value="chroma",
            env_value="pgvector",
            palace_path="/tmp/fake",
            default="sqlite_exact",
        )
        assert result == "qdrant"

    def test_resolve_backend_picks_config_when_no_explicit(self):
        """resolve_backend_for_palace falls back to config value."""
        result = resolve_backend_for_palace(
            explicit=None,
            config_value="pgvector",
            env_value="qdrant",
            palace_path="/tmp/fake",
            default="chroma",
        )
        assert result == "pgvector"

    def test_resolve_backend_picks_env_when_no_explicit_or_config(self):
        """resolve_backend_for_palace falls back to env value."""
        result = resolve_backend_for_palace(
            explicit=None,
            config_value=None,
            env_value="sqlite_exact",
            palace_path=None,
            default="chroma",
        )
        assert result == "sqlite_exact"

    def test_resolve_backend_default_when_nothing_set(self):
        """resolve_backend_for_palace returns default when no prior rule matched."""
        result = resolve_backend_for_palace(
            explicit=None,
            config_value=None,
            env_value=None,
            palace_path=None,
            default="chroma",
        )
        assert result == "chroma"

    def test_get_backend_class(self):
        """get_backend_class returns the class, not an instance."""
        from mempalace.backends.chroma import ChromaBackend

        reset_backends()
        cls = get_backend_class("chroma")
        assert cls is ChromaBackend

    def test_reset_backends_closes_instances(self):
        """reset_backends closes all cached backend instances."""
        reset_backends()
        inst = get_backend("chroma")
        assert not getattr(inst, "_closed", False)
        reset_backends()
        assert getattr(inst, "_closed", True)


# ---------------------------------------------------------------------------
# Error classes from backends/base.py
# ---------------------------------------------------------------------------


class TestBackendErrors:
    """Test error hierarchy and instantiation."""

    def test_backend_error_base(self):
        """BackendError is the base class for all storage-backend errors."""
        err = BackendError("something went wrong")
        assert str(err) == "something went wrong"
        assert isinstance(err, Exception)

    def test_palace_not_found_is_file_not_found(self):
        """PalaceNotFoundError inherits from FileNotFoundError for backward compat."""
        err = PalaceNotFoundError("/path/to/missing")
        assert isinstance(err, FileNotFoundError)
        assert isinstance(err, BackendError)
        assert "/path/to/missing" in str(err)

    def test_collection_not_initialized_hierarchy(self):
        """CollectionNotInitializedError inherits from PalaceNotFoundError."""
        err = CollectionNotInitializedError("test_collection")
        assert isinstance(err, PalaceNotFoundError)
        assert isinstance(err, FileNotFoundError)

    def test_backend_closed_error(self):
        """BackendClosedError is raised when calling a closed backend."""
        err = BackendClosedError("backend has been closed")
        assert "closed" in str(err).lower()

    def test_unsupported_filter_error(self):
        """UnsupportedFilterError for unknown where operators."""
        err = UnsupportedFilterError("operator $custom not supported")
        assert "$custom" in str(err)

    def test_unsupported_capability_error(self):
        """UnsupportedCapabilityError for optional features."""
        err = UnsupportedCapabilityError("lexical_search not available")
        assert "lexical_search" in str(err)

    def test_unsupported_maintenance_kind_error(self):
        """UnsupportedMaintenanceKindError for unknown maintenance ops."""
        err = UnsupportedMaintenanceKindError("kind 'reindex' not supported")
        assert "reindex" in str(err)

    def test_backend_mismatch_error(self):
        """BackendMismatchError for backend/schema mismatches."""
        err = BackendMismatchError("chroma artifact found but pgvector selected")
        assert isinstance(err, BackendError)

    def test_dimension_mismatch_error(self):
        """DimensionMismatchError when embedding dims differ."""
        err = DimensionMismatchError("expected 768 dim, got 384")
        assert isinstance(err, BackendError)

    def test_embedder_identity_mismatch_error(self):
        """EmbedderIdentityMismatchError for model name conflicts."""
        err = EmbedderIdentityMismatchError("collection built with model A, current model is B")
        assert isinstance(err, BackendError)


# ---------------------------------------------------------------------------
# Value-object tests: QueryResult, GetResult, HealthStatus, PalaceRef
# ---------------------------------------------------------------------------


class TestQueryResult:
    """Test QueryResult dataclass and .empty() factory."""

    def test_typed_attributes(self):
        """QueryResult exposes typed ids, documents, metadatas, distances."""
        result = QueryResult(
            ids=[["a", "b"]],
            documents=[["doc1", "doc2"]],
            metadatas=[[{"k": "v"}, {"k2": "v2"}]],
            distances=[[0.1, 0.2]],
        )
        assert result.ids == [["a", "b"]]
        assert result.documents == [["doc1", "doc2"]]
        assert result.metadatas == [[{"k": "v"}, {"k2": "v2"}]]
        assert result.distances == [[0.1, 0.2]]

    def test_empty_factory(self):
        """QueryResult.empty() returns a correctly-shaped empty result."""
        empty = QueryResult.empty(num_queries=2)
        assert len(empty.ids) == 2
        assert empty.ids == [[], []]
        assert empty.documents == [[], []]
        assert empty.metadatas == [[], []]
        assert empty.distances == [[], []]
        assert empty.embeddings is None  # not requested

    def test_empty_with_embeddings(self):
        """QueryResult.empty(embeddings_requested=True) creates empty lists."""
        empty = QueryResult.empty(num_queries=1, embeddings_requested=True)
        assert empty.embeddings == [[]]

    def test_dict_compat_getitem(self):
        """QueryResult supports legacy result['ids'] access."""
        result = QueryResult(
            ids=[["a"]],
            documents=[["doc"]],
            metadatas=[[{}]],
            distances=[[0.5]],
        )
        assert result["ids"] == [["a"]]
        assert result["documents"] == [["doc"]]

    def test_dict_compat_get(self):
        """QueryResult.get('ids') returns the field value."""
        result = QueryResult(ids=[[]], documents=[[]], metadatas=[[]], distances=[[]])
        assert result.get("ids") == [[]]
        assert result.get("nonexistent") is None

    def test_dict_compat_contains(self):
        """QueryResult.__contains__ checks field presence."""
        result = QueryResult(
            ids=[["a"]],
            documents=[["doc"]],
            metadatas=[[{}]],
            distances=[[0.5]],
        )
        assert "ids" in result
        assert "nonexistent" not in result


class TestGetResult:
    """Test GetResult dataclass and .empty() factory."""

    def test_typed_attributes(self):
        """GetResult exposes typed ids, documents, metadatas, embeddings."""
        result = GetResult(
            ids=["a", "b"],
            documents=["doc1", "doc2"],
            metadatas=[{"k": "v"}, {"k2": "v2"}],
        )
        assert result.ids == ["a", "b"]
        assert result.documents == ["doc1", "doc2"]
        assert result.metadatas == [{"k": "v"}, {"k2": "v2"}]

    def test_empty_factory(self):
        """GetResult.empty() returns an all-empty result."""
        empty = GetResult.empty()
        assert empty.ids == []
        assert empty.documents == []
        assert empty.metadatas == []
        assert empty.embeddings is None

    def test_embeddings_field(self):
        """GetResult carries embeddings when provided."""
        result = GetResult(
            ids=["a"],
            documents=["doc"],
            metadatas=[{}],
            embeddings=[[0.1, 0.2, 0.3]],
        )
        assert result.embeddings == [[0.1, 0.2, 0.3]]


class TestHealthStatus:
    """Test HealthStatus value object."""

    def test_healthy(self):
        """HealthStatus.healthy() returns ok=True."""
        h = HealthStatus.healthy("all good")
        assert h.ok
        assert h.detail == "all good"

    def test_unhealthy(self):
        """HealthStatus.unhealthy() returns ok=False."""
        h = HealthStatus.unhealthy("connection refused")
        assert not h.ok
        assert h.detail == "connection refused"

    def test_healthy_no_detail(self):
        """HealthStatus.healthy() works without arguments."""
        h = HealthStatus.healthy()
        assert h.ok
        assert h.detail == ""


class TestPalaceRef:
    """Test PalaceRef value object."""

    def test_minimal(self):
        """PalaceRef can be created with just an id."""
        ref = PalaceRef(id="test-palace")
        assert ref.id == "test-palace"
        assert ref.local_path is None
        assert ref.namespace is None

    def test_full(self):
        """PalaceRef carries local_path and namespace."""
        ref = PalaceRef(
            id="my-palace",
            local_path="/data/palace",
            namespace="tenant-42",
        )
        assert ref.id == "my-palace"
        assert ref.local_path == "/data/palace"
        assert ref.namespace == "tenant-42"

    def test_immutable(self):
        """PalaceRef is a frozen dataclass."""
        ref = PalaceRef(id="test")
        with pytest.raises(Exception):
            ref.id = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ChromaBackend tests (mocked chromadb)
# ---------------------------------------------------------------------------


class TestChromaBackend:
    """Test ChromaBackend with a fully mocked chromadb client."""

    @patch("mempalace.backends.chroma.chromadb")
    def test_get_backend(self, mock_chromadb):
        """get_backend('chroma') returns a ChromaBackend instance."""
        reset_backends()
        backend = get_backend("chroma")
        from mempalace.backends.chroma import ChromaBackend

        assert isinstance(backend, ChromaBackend)

    @patch("mempalace.backends.chroma.chromadb")
    def test_backend_name(self, mock_chromadb):
        """ChromaBackend.name is 'chroma'."""
        from mempalace.backends.chroma import ChromaBackend

        assert ChromaBackend.name == "chroma"

    @patch("mempalace.backends.chroma.chromadb")
    def test_backend_capabilities(self, mock_chromadb):
        """ChromaBackend.capabilities includes expected tokens."""
        from mempalace.backends.chroma import ChromaBackend

        caps = ChromaBackend.capabilities
        assert "supports_embeddings_in" in caps
        assert "supports_metadata_filters" in caps
        assert "supports_lexical_search" in caps
        assert "local_mode" in caps

    @patch("mempalace.backends.chroma.chromadb")
    def test_health_closed(self, mock_chromadb):
        """ChromaBackend.health() is unhealthy when closed."""
        from mempalace.backends.chroma import ChromaBackend

        backend = ChromaBackend()
        backend.close()
        status = backend.health()
        assert not status.ok
        assert "closed" in status.detail

    @patch("mempalace.backends.chroma.os.path.isdir")
    @patch("mempalace.backends.chroma.os.path.isfile")
    @patch("mempalace.backends.chroma.chromadb")
    def test_get_collection_no_create_missing(self, mock_chromadb, mock_isfile, mock_isdir):
        """get_collection(create=False) on missing palace raises PalaceNotFoundError."""
        from mempalace.backends.chroma import ChromaBackend

        mock_isdir.return_value = False
        backend = ChromaBackend()

        with pytest.raises(PalaceNotFoundError):
            backend.get_collection("/nonexistent", "test_coll", create=False)

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_name_consistent(self, mock_chromadb):
        """ChromaCollection wraps the underlying chromadb collection."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        mock_coll.name = "test_collection"
        collection = ChromaCollection(mock_coll)
        assert collection._collection is mock_coll

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_count(self, mock_chromadb):
        """ChromaCollection.count() delegates to the underlying collection."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        mock_coll.count.return_value = 42
        collection = ChromaCollection(mock_coll)
        assert collection.count() == 42
        mock_coll.count.assert_called_once()

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_add(self, mock_chromadb):
        """ChromaCollection.add() delegates to the underlying collection."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        collection = ChromaCollection(mock_coll)

        collection.add(
            documents=["hello world"],
            ids=["doc-1"],
            metadatas=[{"wing": "test"}],
        )
        mock_coll.add.assert_called_once()

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_upsert(self, mock_chromadb):
        """ChromaCollection.upsert() delegates to the underlying collection."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        collection = ChromaCollection(mock_coll)

        collection.upsert(
            documents=["updated content"],
            ids=["doc-1"],
        )
        mock_coll.upsert.assert_called_once()

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_delete_by_ids(self, mock_chromadb):
        """ChromaCollection.delete() with ids delegates to underlying collection."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        collection = ChromaCollection(mock_coll)

        collection.delete(ids=["doc-1", "doc-2"])
        mock_coll.delete.assert_called_once_with(ids=["doc-1", "doc-2"])

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_query(self, mock_chromadb):
        """ChromaCollection.query() returns typed QueryResult."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        mock_coll.query.return_value = {
            "ids": [["a", "b"]],
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"k": "v"}, {"k2": "v2"}]],
            "distances": [[0.1, 0.2]],
        }
        collection = ChromaCollection(mock_coll)

        result = collection.query(query_texts=["test query"], n_results=2)
        assert isinstance(result, QueryResult)
        assert result.ids == [["a", "b"]]

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_get_by_ids(self, mock_chromadb):
        """ChromaCollection.get() with ids returns typed GetResult."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        mock_coll.get.return_value = {
            "ids": ["a"],
            "documents": ["doc1"],
            "metadatas": [{"k": "v"}],
        }
        collection = ChromaCollection(mock_coll)

        result = collection.get(ids=["a"])
        assert isinstance(result, GetResult)
        assert result.ids == ["a"]
        assert result.documents == ["doc1"]

    @patch("mempalace.backends.chroma.chromadb")
    def test_chroma_close_sets_flag(self, mock_chromadb):
        """ChromaBackend.close() sets _closed flag and clears clients."""
        from mempalace.backends.chroma import ChromaBackend

        backend = ChromaBackend()
        assert not backend._closed
        backend.close()
        assert backend._closed

    @patch("mempalace.backends.chroma.chromadb")
    def test_backend_version(self, mock_chromadb):
        """backend_version() returns the chromadb version string."""
        from mempalace.backends.chroma import ChromaBackend

        mock_chromadb.__version__ = "1.5.12"
        assert ChromaBackend.backend_version() == "1.5.12"

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_sanitize_empty_metadata(self, mock_chromadb):
        """ChromaCollection sanitizes empty metadata entries."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        collection = ChromaCollection(mock_coll)

        sanitized = collection._sanitize_metadatas_for_chromadb([None, {}, {"wing": "test"}])
        assert sanitized is not None
        assert sanitized[0] == {"_repaired_empty_meta": True}
        assert sanitized[1] == {"_repaired_empty_meta": True}
        assert sanitized[2] == {"wing": "test"}

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_distance_metric_default(self, mock_chromadb):
        """ChromaCollection reports distance_metric from hnsw:space."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        mock_coll.metadata = {"hnsw:space": "cosine"}
        collection = ChromaCollection(mock_coll)
        assert collection.distance_metric == "cosine"

    @patch("mempalace.backends.chroma.chromadb")
    def test_collection_distance_metric_fallback_l2(self, mock_chromadb):
        """ChromaCollection falls back to 'l2' when hnsw:space is absent."""
        from mempalace.backends.chroma import ChromaCollection

        mock_coll = MagicMock()
        mock_coll.metadata = {}
        collection = ChromaCollection(mock_coll)
        assert collection.distance_metric == "l2"


# ---------------------------------------------------------------------------
# QdrantBackend tests (mocked qdrant_client)
# ---------------------------------------------------------------------------


class TestQdrantBackend:
    """Test QdrantBackend with mocked qdrant_client."""

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_get_backend(self, mock_qdrant_client):
        """get_backend('qdrant') returns a QdrantBackend instance."""
        backend = get_backend("qdrant")
        from mempalace.backends.qdrant import QdrantBackend

        assert isinstance(backend, QdrantBackend)

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_backend_name(self, mock_qdrant_client):
        """QdrantBackend.name is 'qdrant'."""
        from mempalace.backends.qdrant import QdrantBackend

        assert QdrantBackend.name == "qdrant"

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_backend_capabilities(self, mock_qdrant_client):
        """QdrantBackend.capabilities includes expected tokens."""
        from mempalace.backends.qdrant import QdrantBackend

        caps = QdrantBackend.capabilities
        assert "supports_embeddings_in" in caps
        assert "supports_metadata_filters" in caps
        assert "supports_contains_fast" in caps
        assert "remote_mode" in caps

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_health_closed(self, mock_qdrant_client):
        """QdrantBackend.health() is unhealthy when closed."""
        from mempalace.backends.qdrant import QdrantBackend

        backend = QdrantBackend()
        backend.close()
        status = backend.health()
        assert not status.ok
        assert "closed" in status.detail

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_healthy_when_connected(self, mock_qdrant_client):
        """QdrantBackend.health() is healthy when Qdrant responds."""
        from mempalace.backends.qdrant import QdrantBackend

        mock_instance = MagicMock()
        mock_collections = MagicMock()
        mock_collections.collections = ["c1", "c2"]
        mock_instance.get_collections.return_value = mock_collections
        mock_qdrant_client.return_value = mock_instance

        backend = QdrantBackend()
        status = backend.health()
        assert status.ok

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_get_collection_create(self, mock_qdrant_client):
        """QdrantBackend.get_collection(create=True) creates collection."""
        from mempalace.backends.qdrant import QdrantBackend

        mock_instance = MagicMock()
        mock_instance.collection_exists.return_value = False
        mock_qdrant_client.return_value = mock_instance

        backend = QdrantBackend()
        ref = PalaceRef(id="test-palace")
        collection = backend.get_collection(
            palace=ref,
            collection_name="test_coll",
            create=True,
        )
        mock_instance.create_collection.assert_called_once()
        assert collection._name == "test_coll"

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_get_collection_no_create_missing(self, mock_qdrant_client):
        """QdrantBackend.get_collection(create=False) on missing raises."""
        from mempalace.backends.qdrant import QdrantBackend

        mock_instance = MagicMock()
        mock_instance.collection_exists.return_value = False
        mock_qdrant_client.return_value = mock_instance

        backend = QdrantBackend()
        ref = PalaceRef(id="test-palace")

        with pytest.raises(PalaceNotFoundError):
            backend.get_collection(
                palace=ref,
                collection_name="nonexistent",
                create=False,
            )

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_collection_count(self, mock_qdrant_client):
        """QdrantCollection.count() returns point count."""
        from mempalace.backends.qdrant import QdrantBackend, QdrantCollection

        mock_instance = MagicMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 42
        mock_instance.get_collection.return_value = mock_collection_info
        mock_instance.collection_exists.return_value = True
        mock_qdrant_client.return_value = mock_instance

        backend = QdrantBackend()
        collection = QdrantCollection(backend, "test_coll")
        assert collection.count() == 42

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_collection_count_returns_zero_on_error(self, mock_qdrant_client):
        """QdrantCollection.count() returns 0 on exception."""
        from mempalace.backends.qdrant import QdrantBackend, QdrantCollection

        mock_instance = MagicMock()
        mock_instance.get_collection.side_effect = Exception("connection error")
        mock_qdrant_client.return_value = mock_instance

        backend = QdrantBackend()
        collection = QdrantCollection(backend, "test_coll")
        assert collection.count() == 0

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_close_sets_flag(self, mock_qdrant_client):
        """QdrantBackend.close() sets _closed and clears client."""
        from mempalace.backends.qdrant import QdrantBackend

        mock_instance = MagicMock()
        mock_qdrant_client.return_value = mock_instance

        backend = QdrantBackend()
        # Access _lazy_client to initialize the client
        _ = backend._lazy_client
        assert not backend._closed
        backend.close()
        assert backend._closed
        mock_instance.close.assert_called_once()

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_get_collection_via_palace_path(self, mock_qdrant_client):
        """QdrantBackend supports legacy palace_path argument."""
        from mempalace.backends.qdrant import QdrantBackend

        mock_instance = MagicMock()
        mock_instance.collection_exists.return_value = True
        mock_qdrant_client.return_value = mock_instance

        backend = QdrantBackend()
        collection = backend.get_collection("/tmp/palace", "test_coll", create=False)
        assert collection._name == "test_coll"

    @patch("mempalace.backends.qdrant.QdrantClient")
    def test_collection_add_with_embeddings(self, mock_qdrant_client):
        """QdrantCollection.add() with explicit embeddings avoids Ollama call."""
        from mempalace.backends.qdrant import QdrantBackend, QdrantCollection

        mock_instance = MagicMock()
        mock_qdrant_client.return_value = mock_instance

        backend = QdrantBackend()
        collection = QdrantCollection(backend, "test_coll")
        collection.add(
            documents=["hello"],
            ids=["d-1"],
            embeddings=[[0.1] * 768],
        )
        mock_instance.upsert.assert_called_once()


# ---------------------------------------------------------------------------
# PgVectorBackend tests (mocked psycopg)
# ---------------------------------------------------------------------------


class TestPgVectorBackend:
    """Test PgVectorBackend registration and basic attributes."""

    @patch("mempalace.backends.pgvector.os.path.isfile")
    @patch("mempalace.backends.pgvector.os.path.isdir")
    def test_get_backend(self, mock_isdir, mock_isfile):
        """get_backend('pgvector') returns a PgVectorBackend instance."""
        backend = get_backend("pgvector")
        from mempalace.backends.pgvector import PgVectorBackend

        assert isinstance(backend, PgVectorBackend)

    def test_backend_name(self):
        """PgVectorBackend.name is 'pgvector'."""
        from mempalace.backends.pgvector import PgVectorBackend

        assert PgVectorBackend.name == "pgvector"

    def test_backend_capabilities(self):
        """PgVectorBackend.capabilities includes expected tokens."""
        from mempalace.backends.pgvector import PgVectorBackend

        caps = PgVectorBackend.capabilities
        assert "requires_explicit_embeddings" in caps
        assert "supports_embeddings_in" in caps
        assert "supports_metadata_filters" in caps
        assert "supports_namespace_isolation" in caps
        assert "server_mode" in caps
        assert "supports_server_side_indexes" in caps

    def test_maintenance_kinds(self):
        """PgVectorBackend declares analyze and reindex maintenance."""
        from mempalace.backends.pgvector import PgVectorBackend

        kinds = PgVectorBackend.maintenance_kinds
        assert "analyze" in kinds
        assert "reindex" in kinds


# ---------------------------------------------------------------------------
# SQLiteExactBackend tests
# ---------------------------------------------------------------------------


class TestSQLiteExactBackend:
    """Test SQLiteExactBackend registration and basic attributes."""

    def test_get_backend(self):
        """get_backend('sqlite_exact') returns a SQLiteExactBackend instance."""
        backend = get_backend("sqlite_exact")
        from mempalace.backends.sqlite_exact import SQLiteExactBackend

        assert isinstance(backend, SQLiteExactBackend)

    def test_backend_name(self):
        """SQLiteExactBackend.name is 'sqlite_exact'."""
        from mempalace.backends.sqlite_exact import SQLiteExactBackend

        assert SQLiteExactBackend.name == "sqlite_exact"

    def test_backend_capabilities(self):
        """SQLiteExactBackend.capabilities includes expected tokens."""
        from mempalace.backends.sqlite_exact import SQLiteExactBackend

        caps = SQLiteExactBackend.capabilities
        assert "requires_explicit_embeddings" in caps
        assert "supports_embeddings_in" in caps
        assert "supports_metadata_filters" in caps
        assert "supports_lexical_search" in caps
        assert "local_mode" in caps

    def test_maintenance_kinds(self):
        """SQLiteExactBackend declares analyze and compact maintenance."""
        from mempalace.backends.sqlite_exact import SQLiteExactBackend

        kinds = SQLiteExactBackend.maintenance_kinds
        assert "analyze" in kinds
        assert "compact" in kinds


# ---------------------------------------------------------------------------
# LexicalHit / LexicalResult tests
# ---------------------------------------------------------------------------


class TestLexicalResult:
    """Test LexicalHit and LexicalResult value objects."""

    def test_lexical_hit(self):
        """LexicalHit carries id, document, metadata, score."""
        hit = LexicalHit(
            id="doc-1",
            document="sample text",
            metadata={"wing": "test"},
            score=0.85,
        )
        assert hit.id == "doc-1"
        assert hit.document == "sample text"
        assert hit.metadata == {"wing": "test"}
        assert hit.score == 0.85

    def test_lexical_result(self):
        """LexicalResult wraps a list of LexicalHit."""
        hits = [
            LexicalHit(id="a", document="doc a", metadata={}, score=0.9),
            LexicalHit(id="b", document="doc b", metadata={}, score=0.8),
        ]
        result = LexicalResult(hits=hits)
        assert len(result.hits) == 2
        assert result.hits[0].id == "a"
        assert result.hits[1].score == 0.8


# ---------------------------------------------------------------------------
# MaintenanceResult tests
# ---------------------------------------------------------------------------


class TestMaintenanceResult:
    """Test MaintenanceResult dataclass."""

    def test_ran_status(self):
        """MaintenanceResult with status 'ran'."""
        result = MaintenanceResult(kind="analyze", status="ran", stats={"rows": 100})
        assert result.kind == "analyze"
        assert result.status == "ran"
        assert result.stats == {"rows": 100}

    def test_already_running(self):
        """MaintenanceResult with status 'already_running'."""
        result = MaintenanceResult(kind="reindex", status="already_running")
        assert result.status == "already_running"

    def test_noop(self):
        """MaintenanceResult with status 'noop'."""
        result = MaintenanceResult(kind="compact", status="noop")
        assert result.status == "noop"


# ---------------------------------------------------------------------------
# EmbedderIdentity / check_embedder_identity tests
# ---------------------------------------------------------------------------


class TestEmbedderIdentity:
    """Test EmbedderIdentity dataclass and check_embedder_identity function."""

    def test_embedder_identity_minimal(self):
        """EmbedderIdentity can be created with just model_name."""
        ei = EmbedderIdentity(model_name="nomic-embed-text")
        assert ei.model_name == "nomic-embed-text"
        assert ei.dimension == 0

    def test_embedder_identity_full(self):
        """EmbedderIdentity with both model_name and dimension."""
        ei = EmbedderIdentity(model_name="nomic-embed-text", dimension=768)
        assert ei.dimension == 768

    def test_check_identify_unknown_when_none(self):
        """check_embedder_identity returns 'unknown' when stored is None."""
        current = EmbedderIdentity(model_name="nomic-embed-text", dimension=768)
        assert check_embedder_identity(None, current) == "unknown"

    def test_check_identify_match(self):
        """check_embedder_identity returns 'known_match' when identical."""
        stored = EmbedderIdentity(model_name="nomic-embed-text", dimension=768)
        current = EmbedderIdentity(model_name="nomic-embed-text", dimension=768)
        assert check_embedder_identity(stored, current) == "known_match"

    def test_check_identify_dimension_mismatch_raises(self):
        """Dimension mismatch raises DimensionMismatchError."""
        stored = EmbedderIdentity(model_name="nomic-embed-text", dimension=768)
        current = EmbedderIdentity(model_name="nomic-embed-text", dimension=384)
        with pytest.raises(DimensionMismatchError):
            check_embedder_identity(stored, current)

    def test_check_identify_model_mismatch_raises(self):
        """Model name mismatch raises EmbedderIdentityMismatchError."""
        stored = EmbedderIdentity(model_name="model-a", dimension=768)
        current = EmbedderIdentity(model_name="model-b", dimension=768)
        with pytest.raises(EmbedderIdentityMismatchError):
            check_embedder_identity(stored, current)

    def test_check_identify_force_swap_returns_mismatch(self):
        """force_model_swap=True returns 'known_mismatch' instead of raising."""
        stored = EmbedderIdentity(model_name="model-a", dimension=768)
        current = EmbedderIdentity(model_name="model-b", dimension=768)
        result = check_embedder_identity(stored, current, force_model_swap=True)
        assert result == "known_mismatch"

    def test_check_identify_unknown_when_current_has_no_model(self):
        """check_embedder_identity returns 'unknown' when current embedder is unnamed."""
        stored = EmbedderIdentity(model_name="model-a", dimension=768)
        current = EmbedderIdentity(model_name="", dimension=768)
        assert check_embedder_identity(stored, current) == "unknown"


# ---------------------------------------------------------------------------
# BaseCollection default method tests
# ---------------------------------------------------------------------------


class TestBaseCollectionDefaultMethods:
    """Test default implementations on BaseCollection."""

    @pytest.fixture
    def collection(self):
        return _ConcreteCollection()

    def test_estimated_count_defaults_to_count(self):
        """estimated_count() defaults to count()."""
        collection = _ConcreteCollection()
        assert collection.estimated_count() == 0

    def test_distance_metric_default(self):
        """Default distance_metric is 'cosine'."""
        collection = _ConcreteCollection()
        assert collection.distance_metric == "cosine"

    def test_health_default(self):
        """Default health() returns healthy."""
        collection = _ConcreteCollection()
        status = collection.health()
        assert status.ok

    def test_close_default(self):
        """Default close() is a no-op (returns None)."""
        collection = _ConcreteCollection()
        result = collection.close()
        assert result is None

    def test_get_stored_embedder_identity_default(self):
        """Default get_stored_embedder_identity() returns None."""
        collection = _ConcreteCollection()
        assert collection.get_stored_embedder_identity() is None

    def test_set_embedder_identity_default(self):
        """Default set_embedder_identity() is a no-op."""
        collection = _ConcreteCollection()
        # Should not raise
        collection.set_embedder_identity(EmbedderIdentity(model_name="test", dimension=768))

    def test_run_maintenance_raises(self):
        """Default run_maintenance raises UnsupportedMaintenanceKindError."""
        collection = _ConcreteCollection()
        with pytest.raises(UnsupportedMaintenanceKindError):
            collection.run_maintenance("analyze")

    def test_lexical_search_raises(self):
        """Default lexical_search raises UnsupportedCapabilityError."""
        collection = _ConcreteCollection()
        with pytest.raises(UnsupportedCapabilityError):
            collection.lexical_search(query="test")

    def test_update_default_requires_args(self):
        """Default update() raises ValueError with no arguments."""
        collection = _ConcreteCollection()
        with pytest.raises(ValueError, match="requires at least one"):
            collection.update(ids=["a", "b"])

    def test_update_default_requires_length_match(self):
        """Default update() raises ValueError on length mismatch."""
        collection = _ConcreteCollection()
        # documents length doesn't match ids length, should raise
        with pytest.raises(ValueError, match="length"):
            collection.update(ids=["a", "b"], documents=["only_one"])

    def test_maintenance_state_default(self):
        """Default maintenance_state() returns empty dict."""
        collection = _ConcreteCollection()
        assert collection.maintenance_state() == {}

    def test_effective_embedder_identity_default(self):
        """Default effective_embedder_identity() returns None."""
        collection = _ConcreteCollection()
        assert collection.effective_embedder_identity() is None

    def test_get_all_metadata_default(self):
        """Default get_all_metadata() works on empty collection."""
        collection = _ConcreteCollection()
        assert collection.get_all_metadata() == []


# ---------------------------------------------------------------------------
# BaseBackend default method tests
# ---------------------------------------------------------------------------


class TestBaseBackendDefaultMethods:
    """Test default implementations on BaseBackend."""

    def test_default_health(self):
        """Default BaseBackend.health() returns healthy."""
        backend = _ConcreteBackend()
        status = backend.health()
        assert status.ok

    def test_default_close(self):
        """Default BaseBackend.close() is a no-op."""
        backend = _ConcreteBackend()
        result = backend.close()
        assert result is None

    def test_default_close_palace(self):
        """Default BaseBackend.close_palace() is a no-op."""
        backend = _ConcreteBackend()
        ref = PalaceRef(id="test")
        result = backend.close_palace(ref)
        assert result is None

    def test_detect_default(self):
        """Default BaseBackend.detect() returns False."""
        assert not BaseBackend.detect("/some/path")

    def test_distance_metric_default(self):
        """Default BaseBackend.distance_metric is 'cosine'."""
        from mempalace.backends.base import BaseBackend

        assert BaseBackend.distance_metric == "cosine"

    def test_maintenance_kinds_default(self):
        """Default BaseBackend.maintenance_kinds is empty."""
        from mempalace.backends.base import BaseBackend

        assert BaseBackend.maintenance_kinds == frozenset()

    def test_spec_version_default(self):
        """Default BaseBackend.spec_version is '1.0'."""
        from mempalace.backends.base import BaseBackend

        assert BaseBackend.spec_version == "1.0"


# ---------------------------------------------------------------------------
# EmbedderIdentity check edge cases
# ---------------------------------------------------------------------------


class TestEmbedderIdentityEdgeCases:
    """Edge-case tests for check_embedder_identity."""

    def test_both_none_stored(self):
        """When both stored and current are None/empty, returns 'unknown'."""
        assert check_embedder_identity(None, None) == "unknown"

    def test_dimension_zero_skipped(self):
        """Zero dimension on either side is skipped (treated as unknown)."""
        stored = EmbedderIdentity(model_name="same", dimension=0)
        current = EmbedderIdentity(model_name="same", dimension=768)
        # Both have same model name; dim 0 is "unknown", so it's a match
        assert check_embedder_identity(stored, current) == "known_match"

    def test_model_mismatch_with_zero_dim(self):
        """Model name mismatch still raises even when dim is zero."""
        stored = EmbedderIdentity(model_name="model-a", dimension=0)
        current = EmbedderIdentity(model_name="model-b", dimension=768)
        with pytest.raises(EmbedderIdentityMismatchError):
            check_embedder_identity(stored, current)


# ---------------------------------------------------------------------------
# CollectionNotInitializedError specifics
# ---------------------------------------------------------------------------


class TestCollectionNotInitialized:
    """Tests specific to CollectionNotInitializedError."""

    def test_message_contains_collection_name(self):
        """Error message includes the collection name."""
        err = CollectionNotInitializedError("my_collection")
        assert "my_collection" in str(err)

    def test_is_palace_not_found(self):
        """Instance check passes for PalaceNotFoundError."""
        err = CollectionNotInitializedError("test")
        assert isinstance(err, PalaceNotFoundError)


# ---------------------------------------------------------------------------
# HealthStatus edge cases
# ---------------------------------------------------------------------------


class TestHealthStatusEdgeCases:
    """Additional HealthStatus tests."""

    def test_default_detail_empty(self):
        """Default detail is empty string."""
        h = HealthStatus.healthy()
        assert h.detail == ""

    def test_unhealthy_detail_preserved(self):
        """Unhealthy detail is preserved."""
        h = HealthStatus.unhealthy("disk full")
        assert h.detail == "disk full"


# ---------------------------------------------------------------------------
# _IncludeSpec tests (private helper used by all backends)
# ---------------------------------------------------------------------------


class TestIncludeSpec:
    """Test the _IncludeSpec resolution helper used by all backends."""

    def test_default_include(self):
        """Default include resolves documents, metadatas, distances; no embeddings."""
        from mempalace.backends.base import _IncludeSpec

        spec = _IncludeSpec.resolve(None)
        assert spec.documents
        assert spec.metadatas
        assert spec.distances
        assert not spec.embeddings

    def test_custom_include(self):
        """Custom include respects only the requested keys."""
        from mempalace.backends.base import _IncludeSpec

        spec = _IncludeSpec.resolve(["embeddings", "metadatas"])
        assert not spec.documents
        assert spec.metadatas
        assert not spec.distances
        assert spec.embeddings

    def test_empty_include(self):
        """Empty include list means nothing requested."""
        from mempalace.backends.base import _IncludeSpec

        spec = _IncludeSpec.resolve([])
        assert not spec.documents
        assert not spec.metadatas
        assert not spec.distances
        assert not spec.embeddings

    def test_default_distances_false_for_get(self):
        """get() queries resolve with default_distances=False."""
        from mempalace.backends.base import _IncludeSpec

        spec = _IncludeSpec.resolve(None, default_distances=False)
        assert not spec.distances


# ---------------------------------------------------------------------------
# Embedder Protocol tests
# ---------------------------------------------------------------------------


class TestEmbedderProtocol:
    """Test the Embedder runtime-checkable protocol."""

    def test_embedder_protocol_matches(self):
        """An object with model_name, dimension, and embed() matches Embedder."""
        from mempalace.backends.base import Embedder

        class FakeEmbedder:
            model_name = "test-model"
            dimension = 768

            def embed(self, texts):
                return [[0.0] * 768 for _ in texts]

        assert isinstance(FakeEmbedder(), Embedder)

    def test_embedder_protocol_no_match(self):
        """An object without embed() does not match Embedder."""
        from mempalace.backends.base import Embedder

        class NotAnEmbedder:
            model_name = "test"

        assert not isinstance(NotAnEmbedder(), Embedder)
