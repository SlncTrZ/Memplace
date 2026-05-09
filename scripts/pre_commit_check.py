#!/usr/bin/env python3
"""Pre-commit hook: Detect API keys in staged files.

Wing: openclaw
Topic: security_check
Last Updated: 2026-05-09
"""

import os
import re
import subprocess
import sys

# Patterns to detect API keys/credentials
PATTERNS = [
    re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']([^"\']{16,})["\']', re.IGNORECASE),
    re.compile(r'secret["\']?\s*[:=]\s*["\']([^"\']{16,})["\']', re.IGNORECASE),
    re.compile(r'token["\']?\s*[:=]\s*["\']([^"\']{20,})["\']', re.IGNORECASE),
    re.compile(r'password["\']?\s*[:=]\s*["\']([^"\']{8,})["\']', re.IGNORECASE),
    re.compile(r'QDRANT_API_KEY\s*=\s*["\']([^"\']+)["\']'),
    re.compile(r'OLLAMA_API_KEY\s*=\s*["\']([^"\']+)["\']'),
]

# Files to ignore
IGNORE_FILES = ['.env.example', 'pre_commit_check.py', '*.key', '*_secrets*']


def check_file(filepath):
    """Check file for API keys."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        for i, line in enumerate(content.split('\n'), 1):
            for pattern in PATTERNS:
                match = pattern.search(line)
                if match:
                    # Skip if it's a placeholder/example
                    key_value = match.group(1)
                    if any(placeholder in key_value.lower() 
                           for placeholder in ['your_', 'example', 'placeholder', 'xxx']):
                        continue
                    return True, i, line.strip()
        return False, None, None
    except Exception:
        return False, None, None


def main():
    """Check staged files for API keys."""
    try:
        # Get staged files
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACM'],
            capture_output=True, text=True, check=True
        )
        staged_files = result.stdout.strip().split('\n')
        
        if not staged_files or staged_files == ['']:
            print("✓ No files staged for commit")
            return 0
        
        checked = 0
        errors = []
        
        for filepath in staged_files:
            if any(filepath.endswith(ext) for ext in ['.py', '.json', '.yaml', '.yml', '.txt', '.md', '.env']):
                if any(ig in filepath for ig in IGNORE_FILES):
                    continue
                    
                has_key, line_num, line = check_file(filepath)
                if has_key:
                    errors.append((filepath, line_num, line))
                checked += 1
        
        if errors:
            print("❌ SECURITY ERROR: API keys detected in staged files!")
            print("\nFound potential secrets:")
            for filepath, line_num, line in errors:
                print(f"  {filepath}:{line_num}")
                print(f"    {line[:100]}...")
            print("\nPlease:")
            print("  1. Remove the API key from the file")
            print("  2. Use environment variables (.env file)")
            print("  3. Update .gitignore if needed")
            print("\nCommit blocked.")
            return 1
        
        print(f"✓ Checked {checked} files - no API keys detected")
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"Error running git command: {e}")
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
