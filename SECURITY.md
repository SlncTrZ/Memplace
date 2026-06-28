# Security Guide

## Protecting API Keys When Public/Committing GitHub Repo

### 🔴 CRITICAL RULES

1. **NEVER commit `.env` file** - contains real API keys
2. **NEVER hardcode API keys** in Python/JSON/YAML files
3. **ALWAYS use `.env.example`** with placeholder values
4. **ALWAYS verify `.gitignore`** blocks sensitive files

### ✅ DO'S

```bash
# 1. Create .env from template
cp .env.example .env

# 2. Fill in actual values in .env (NOT .env.example)
echo 'QDRANT_API_KEY=real_key_here' >> .env

# 3. .env is already in .gitignore ✓
git status  # .env should NOT appear
```

### ❌ DON'TS

```python
# ❌ NEVER hardcode in Python
QDRANT_API_KEY = "real_key_12345"  # BAD!

# ✅ Use environment variables
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")  # GOOD!
```

```json
// ❌ NEVER hardcode in JSON
{
  "api_key": "real_key_12345"  // BAD!
}

// ✅ Use env var references in your app code
```

### Pre-Commit Protection

Install the pre-commit hook to automatically detect API keys:

```bash
# Make executable
chmod +x scripts/pre_commit_check.py

# Install hook
ln -s ../../scripts/pre_commit_check.py .git/hooks/pre-commit

# Test
python scripts/pre_commit_check.py
```

The hook will:

- ✅ Block commits containing API keys
- ✅ Allow placeholders (`your_key_here`, `example`)
- ✅ Check `.py`, `.json`, `.yaml`, `.yml`, `.env` files
- ❌ Not check `.env.example` (it's safe)

### Verify Before Commit

```bash
# 1. Check what will be committed
git diff --cached --name-only

# 2. Manually scan for secrets
git diff --cached | grep -i 'api[_-]?key\|secret\|token'

# 3. Run pre-commit check manually
python scripts/pre_commit_check.py

# 4. Commit
git commit -m "feat: add feature"
```

### Emergency: Accidentally Committed?

```bash
# 1. Remove from current commit (most recent)
git reset --soft HEAD~1
rm .env
git add .
git commit -m "feat: add feature"

# 2. If already pushed - REVOKED KEY IMMEDIATELY!
# Then:
git filter-branch --force --index-filter \
  'git rm --cached --ignore-unmatch .env' \
  --prune-empty --tag-name-filter cat -- --all

# Force push (WARNING: rewrites history)
git push origin --force --all

# 3. Generate new API key
# 4. Update Qdrant with new key
```

### Public Repo Checklist

Before creating PR or pushing to public GitHub:

- [ ] `.env` is NOT in git status
- [ ] `.env.example` contains only placeholders
- [ ] `.gitignore` includes: `.env`, `*.key`, `*_secrets.json`
- [ ] No hardcoded keys in code (grep: `api[_-]?key.*[=:].*['"][^'"]+['"]`)
- [ ] Pre-commit hook installed
- [ ] Test commit passes pre-commit check

### Environment Variables Reference

```bash
# Required for operation
QDRANT_URL=http://localhost:6333        # Replace with your Qdrant server
QDRANT_API_KEY=<your_real_key>         # ⚠️ SENSITIVE
OLLAMA_URL=http://localhost:11434       # Replace with your Ollama
EMBED_MODEL=nomic-embed-text:latest

# Optional: Custom wings
WING_COLLECTIONS={"wing1": "meilin_wing1", "wing2": "meilin_wing2"}
```

### For Contributors

If you need to test MemPlace with your own Qdrant:

1. Fork the repo
2. Copy `.env.example` → `.env`
3. Add your keys to `.env`
4. Test locally
5. **NEVER commit `.env`**
6. PR your code changes only (not config)

### For Users (Installation)

```bash
# Install
pip install -e ".[dev]"

# Setup env
cp .env.example .env
# Edit .env with your keys

# Install pre-commit hook (recommended)
chmod +x scripts/pre_commit_check.py
ln -s ../../scripts/pre_commit_check.py .git/hooks/pre-commit

# Run
python -m mempalace
```

### Qdrant Security Tips

1. **Use API keys** - Qdrant supports authentication
2. **Network isolation** - Run Qdrant in private network
3. **TLS/SSL** - Enable HTTPS for Qdrant REST API
4. **Firewall** - Restrict access to Qdrant port (6333)
5. **Regular rotation** - Change API keys periodically

### Reporting Security Issues

If you find a security vulnerability:

1. **DO NOT** create public issue/PR
2. Open a [GitHub Security Advisory](https://github.com/SlncTrZ/Memplace/security/advisories)
3. Include: description, reproduction steps, impact
4. Wait for fix before disclosure
