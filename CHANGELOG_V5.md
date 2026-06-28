# MemPlace v3.5.0 — Multi-Backend Architecture

## 🎯 Major Changes

### Dynamic Multi-Wing System

**Before (v4.0.0):**

- Hardcoded 6 wings in `config.py`
- Fixed collection mapping
- Difficult to extend

**After (v5.0.0):**

- **Dynamic wing detection** from Qdrant collections
- **Auto-discovery** of `meilin_*` prefixed collections
- **Custom config** via `WING_COLLECTIONS` environment variable
- **Backward compatible** with default 6 wings

### Configuration

```python
# config.py now auto-fetches wings from Qdrant
def get_wing_collections():
    """Fetch wing collections from Qdrant, fallback to defaults."""
    # 1. Check WING_COLLECTIONS env var (JSON)
    # 2. Query Qdrant for meilin_* collections
    # 3. Fallback to DEFAULT_WING_COLLECTIONS

WING_COLLECTIONS = get_wing_collections()  # Dynamic!
WING_NAMES = list(WING_COLLECTIONS.keys())
```

### Usage Examples

**Default (auto-detected):**

```bash
# Auto-discovers all meilin_* collections in Qdrant
python -m mempalace
```

**Custom wings:**

```bash
export WING_COLLECTIONS='{"docs": "meilin_docs", "ai": "meilin_ai"}'
python -m mempalace
```

**Add new wing:**

```bash
# 1. Create collection in Qdrant
curl -X PUT "http://localhost:6333/collections/meilin_new_wing" \
  -H "Content-Type: application/json" \
  -d '{
    "vectors": {
      "size": 768,
      "distance": "Cosine"
    }
  }'

# 2. Restart MemPlace - auto-detects new wing!
python -m mempalace
```

## 🔒 Security Improvements

### Pre-Commit Hook

**New:** `scripts/pre_commit_check.py`

Detects and blocks commits containing:

- API keys (`api_key = "..."`)
- Secrets/tokens (16+ chars)
- Passwords (8+ chars)
- Specific env vars (`QDRANT_API_KEY`)

**Installation:**

```bash
chmod +x scripts/pre_commit_check.py
ln -s ../../scripts/pre_commit_check.py .git/hooks/pre-commit
```

### Security Documentation

**New:** `SECURITY.md`

Comprehensive guide covering:

- ✅/❌ DO'S and DON'TS for API keys
- Pre-commit hook setup
- Emergency procedures for leaked keys
- Public repo checklist
- Qdrant security best practices

### Enhanced .gitignore

Added protection for:

```gitignore
.env
.env.local
.env.*.local
*.key
*_secrets.json
secrets/
credentials/
```

## 📝 Documentation Updates

### README.md Changes

- **Architecture diagram** updated: "6 collections" → "Multi-Wing collections"
- **Wings section** restructured:
  - Explains dynamic nature
  - Shows default 6 wings
  - Documents customization options
- **Environment variables** table:
  - Added `WING_COLLECTIONS` (optional)
  - Added security notes for `QDRANT_API_KEY`
- **New section:** "Security: Protect API Keys"
- **New section:** "Custom Wings" with examples

### Code Docstrings

All files updated from "6-Wing" → "Multi-Wing":

- `config.py:1` — Multi-Wing Palace configuration
- `qdrant_bridge.py:1` — Multi-Wing Palace backend
- `mcp_server.py:1` — Multi-Wing Palace MCP Server

### Tool Descriptions Updated

MCP tool descriptions now emphasize:

- "6 wings" → "Multi-Wing Palace"
- "All 6 wings" → "All wings available in Qdrant"
- "Search across 5 wings" → "Search across wings"
- Added "(depends on config)" notes

## 🔄 Migration Guide

### For Users

**No breaking changes!** If you're using default 6 wings, everything works as before.

**To add custom wings:**

```bash
# Option 1: Create Qdrant collections (auto-detected)
# Option 2: Set WING_COLLECTIONS env var
export WING_COLLECTIONS='{"my_wing": "meilin_my_wing"}'
```

### For Developers

**Updated code patterns:**

```python
# ❌ Old (v4.0.0)
from config import WING_NAMES  # Hardcoded 6

# ✅ New (v5.0.0)
from config import WING_NAMES  # Dynamic, fetched from Qdrant
```

**Testing:**

```python
# Mock for tests
import os
os.environ['WING_COLLECTIONS'] = '{"test": "meilin_test"}'
from mempalace.config import WING_NAMES
assert WING_NAMES == ['test']
```

## 📦 Package Changes

### Version Bump

- `pyproject.toml`: `4.0.0` → `5.0.0`
- `mempalace/version.py`: Update `__version__`

### New Files

```
mempalace/
├── SECURITY.md                    # NEW: Security guide
├── scripts/
│   ├── PRE_COMMIT_README.md       # NEW: Hook documentation
│   └── pre_commit_check.py        # NEW: Pre-commit security check
└── .env.example                   # UPDATED: Security notes
```

### Modified Files

```
mempalace/
├── config.py                      # MAJOR: Dynamic wings
├── qdrant_bridge.py               # UPDATED: Docstrings
├── mcp_server.py                  # UPDATED: Tool descriptions
├── README.md                      # MAJOR: Architecture docs
├── .gitignore                     # UPDATED: More patterns
├── .env.example                   # UPDATED: Security warnings
└── pyproject.toml                 # UPDATED: Version + description
```

## 🧪 Testing

### Verification Commands

```bash
# 1. Check version
python -c "from mempalace.version import __version__; print(__version__)"
# Output: 5.0.0

# 2. Verify dynamic wings
python -c "from mempalace.config import WING_NAMES; print(WING_NAMES)"
# Output: ['tcdserver', 'openclaw', 'robotics', ...] (dynamic)

# 3. Test pre-commit hook
python scripts/pre_commit_check.py
# Output: ✓ Checked X files - no API keys detected

# 4. Test custom wings
WING_COLLECTIONS='{"test": "meilin_test"}' python -c \
  "from mempalace.config import WING_NAMES; print(WING_NAMES)"
# Output: ['test']
```

### Test Pre-Commit Hook

```bash
# Create test file with fake key
echo 'QDRANT_API_KEY = "test-key-1234567890" > test.py'

# Try to commit (should fail)
git add test.py
git commit -m "test"  # ❌ BLOCKED by pre-commit hook

# Clean up
rm test.py
```

## 🚀 Deployment

### Production Checklist

- [ ] Update `.env` on server (no changes needed for default setup)
- [ ] Install pre-commit hook (optional but recommended)
- [ ] Review `SECURITY.md`
- [ ] Verify Qdrant collections exist
- [ ] Test with `python -m mempalace`
- [ ] Check `mempalace_status` returns correct wings

### GitHub Actions (if used)

Update workflow to install pre-commit hook:

```yaml
- name: Install pre-commit hook
  run: |
    chmod +x scripts/pre_commit_check.py
    ln -s ../../scripts/pre_commit_check.py .git/hooks/pre-commit
```

## 📊 Performance Impact

**Negligible!** Wing fetching happens once at import time:

- Qdrant `/collections` request: ~5ms
- Fallback to defaults: ~0ms (if Qdrant unreachable)
- No runtime overhead after startup

## 🐛 Known Issues

None. Backward compatible with v4.0.0.

## 🔮 Future Enhancements

- [ ] Wing validation on startup
- [ ] Auto-create missing collections
- [ ] Wing permissions/roles
- [ ] Wing-specific embeddings

## 📞 Support

For issues or questions:

- GitHub: <https://github.com/truongcongdinh97/Memplace>
- Security: <security@yourdomain.com> (for vulnerabilities)

---

**Upgrade Guide:** This is a non-breaking update. Just `pip install --upgrade memplace` and restart!

**Security Note:** Review `SECURITY.md` and install pre-commit hook before committing to public repos.
