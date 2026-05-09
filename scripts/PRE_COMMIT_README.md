# Pre-commit Hook Setup

This script helps prevent committing API keys and secrets to the repository.

## Installation

1. **Make executable:**
   ```bash
   chmod +x scripts/pre_commit_check.py
   ```

2. **Install as git pre-commit hook:**
   ```bash
   ln -s ../../scripts/pre_commit_check.py .git/hooks/pre-commit
   ```

   Or on Windows (Git Bash):
   ```bash
   ln -s ../../scripts/pre_commit_check.py .git/hooks/pre-commit
   ```

3. **Verify:**
   ```bash
   ls -la .git/hooks/pre-commit
   ```

## What It Checks

- API keys in format: `api_key = "..."`, `api-key: "..."`, etc.
- Secrets and tokens (16+ characters)
- Passwords (8+ characters)
- Specific env vars: `QDRANT_API_KEY`, `OLLAMA_API_KEY`
- Ignores: placeholders (`your_key`, `example`), `.env.example`, test files

## Pattern Examples

**❌ Blocked (commit prevented):**
```python
QDRANT_API_KEY = "real-secret-key-1234567890"
```

**✅ Allowed (placeholder):**
```python
QDRANT_API_KEY = "your_qdrant_api_key_here"
```

**✅ Allowed (environment variable):**
```python
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")
```

## Testing

```bash
# Test hook (won't block if no secrets)
git commit --dry-run -m "test"

# Simulate a secret (this will fail)
echo 'QDRANT_API_KEY = "test-key-1234567890" >> test_secret.py
git add test_secret.py
git commit -m "test secret"  # ❌ Blocked
```

## Manual Run

```bash
python scripts/pre_commit_check.py
```

## Disable Hook (Temporary)

If needed, bypass with `--no-verify`:
```bash
git commit --no-verify -m "message"
```

**⚠️ WARNING: Only use `--no-verify` if you're absolutely sure no secrets are being committed!**
