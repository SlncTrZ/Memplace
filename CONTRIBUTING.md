# Contributing to MemPalace

Cảm ơn bạn đã quan tâm đến dự án MemPalace!

## Yêu cầu

- Python 3.9+
- Qdrant server (local hoặc remote)
- Ollama (cho embedding, optional)

## Thiết lập môi trường

```bash
# Clone repository
git clone https://github.com/truongcongdinh97/Memplace.git
cd Memplace

# Cài đặt với dev dependencies
pip install -e ".[dev]"

# Copy và cấu hình environment
cp .env.example .env
# Chỉnh sửa .env với thông tin Qdrant/Ollama của bạn

# Chạy tests
python -m pytest tests/ -v
```

## Kiến trúc

MemPalace sử dụng kiến trúc **6-Wing Knowledge Palace** với Qdrant:

| Wing | Collection | Purpose |
|------|-----------|---------|
| tcdserver | meilin_tcdserver | Server infrastructure |
| openclaw | meilin_openclaw | AI/MeiLin knowledge |
| robotics | meilin_robotics | Robotics & hardware |
| code_chronicles | meilin_code_chronicles | Code history |
| omniscience_wiki | meilin_omniscience_wiki | General knowledge |
| conversation | meilin_conversation | Conversation memory |

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

## MCP Tools

Khi thêm MCP tool mới:

1. Định nghĩa tool trong `mempalace/mcp_server.py`
2. Thêm tests trong `tests/test_mcp_server.py`
3. Cập nhật README.md danh sách tools

## Commit Convention

| Prefix | Mô tả |
|--------|--------|
| `feat:` | Tính năng mới |
| `fix:` | Sửa bug |
| `docs:` | Documentation |
| `refactor:` | Refactor code |
| `test:` | Thêm/sửa tests |
| `chore:` | Build, dependencies |
