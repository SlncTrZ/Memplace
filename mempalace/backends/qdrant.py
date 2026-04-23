import os
import requests
import uuid
import hashlib
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

class QdrantBackend:
    def __init__(self, palace_path=None):
        self.ollama_url = "http://localhost:11434/api/embeddings"
        # Không hardcode collection ở đây nữa
        self.api_key = os.getenv("QDRANT_API_KEY", "wQ72uGxOv1kpX5ETBo1FEuKeYWf8ytac11cJIcOg")
        self.client = QdrantClient(
            url="http://localhost:6333",
            api_key=self.api_key
        )

    def _get_embedding(self, text):
        try:
            r = requests.post(
                self.ollama_url,
                json={"model": "nomic-embed-text", "prompt": text},
                timeout=30.0
            )
            return r.json()["embedding"]
        except Exception as e:
            print(f"❌ Ollama Error: {e}")
            return None

    def get_collection(self, palace_path, collection_name=None, create=True):
        # Lấy tên từ framework truyền xuống
        name = collection_name or "mempalace_drawers"
        
        # TỰ ĐỘNG KHỞI TẠO NẾU CHƯA CÓ
        if create and not self.client.collection_exists(name):
            self.client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=768, distance=Distance.COSINE),
            )
        return QdrantCollection(self, name)

class QdrantCollection:
    def __init__(self, backend, name):
        self.backend = backend
        self.name = name

    def upsert(self, ids, documents, metadatas=None):
        for i, doc in enumerate(documents):
            vector = self.backend._get_embedding(doc)
            if vector:
                raw_id = ids[i] if ids[i] else str(uuid.uuid4())
                try:
                    point_id = str(uuid.UUID(str(raw_id)))
                except (ValueError, AttributeError):
                    hash_md5 = hashlib.md5(str(raw_id).encode()).hexdigest()
                    point_id = str(uuid.UUID(hash_md5))

                self.backend.client.upsert(
                    collection_name=self.name,
                    points=[PointStruct(
                        id=point_id,
                        vector=vector,
                        payload={
                            "document": doc, 
                            "metadata": metadatas[i] if metadatas else {}
                        }
                    )]
                )

    def query(self, query_texts, n_results=5):
        vector = self.backend._get_embedding(query_texts[0])
        if not vector: return {"documents": [[]]}
        results = self.backend.client.query_points(
            collection_name=self.name,
            query=vector,
            limit=n_results,
            with_payload=True
        )
        return {
            "documents": [[res.payload["document"] for res in results.points]],
            "metadatas": [[res.payload["metadata"] for res in results.points]],
            "ids": [[res.id for res in results.points]]
        }