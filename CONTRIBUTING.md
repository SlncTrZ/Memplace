# Contributing to MemPalace

Cảm ơn bạn đã quan tâm đến dự án MemPalace!

## Yêu cầu

- Python 3.10+
- Palace backend: Qdrant (default), PgVector, SQLite Exact
- Ollama (optional, cho embedding) | ONNX model local (default, zero-dependency)

## Thiết lập môi trường

```bash
# Clone repository
git clone https://github.com/SlncTrZ/Memplace.git
cd Memplace

# Cài đặt với dev dependencies
pip install -e ".[dev]"

# Chạy tests (default Chroma backend — không cần config)
python -m pytest tests/ -v
```

## Kiến trúc

MemPalace sử dụng kiến trúc **Qdrant Palace**:

- **Palace** — stores verbatim content (drawers) in rooms within wings
  - Backends: Qdrant (default), PgVector, SQLite Exact
- **Knowledge Graph** — temporal entity relationships (SQLite)
- **Palace Graph** — room-to-room navigation, cross-wing tunnels

Default backend (Qdrant) — deploy với Docker Qdrant hoặc local server.

## Quy trình phát triển

### 1. Tạo Branch

```bash
git checkout -b feature/ten-feature
```

### 2. Thực hiện thay đổi

- Tuân theo code style (ruff, line-length 100)
- Viết tests cho functionality mới
- Cập nhật docs nếu cần

### 3. Kiểm tra chất lượng

```bash
# Lint
ruff check mempalace/

# Format
ruff format mempalace/

# Tests với coverage
python -m pytest tests/ -v --cov=mempalace
```

### 4. Commit & Push

```bash
git add .
git commit -m "feat: mô tả ngắn gọn"
git push origin feature/ten-feature
```

## MCP Tools (30 tools)

Khi thêm MCP tool mới:

1. Định nghĩa tool trong `mempalace/mcp_server.py` (thêm vào `TOOLS` dict + viết handler function)
2. Thêm tests trong `tests/test_mcp_server.py`
3. Cập nhật danh sách tools trong `README.md` và `mempalace/instructions/help.md`

## Commit Convention

| Prefix | Mô tả |
|--------|--------|
| `feat:` | Tính năng mới |
| `fix:` | Sửa bug |
| `docs:` | Documentation |
| `refactor:` | Refactor code |
| `test:` | Thêm/sửa tests |
| `chore:` | Build, dependencies |
