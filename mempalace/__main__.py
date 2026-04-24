"""__main__ — CLI entry point for mempalace.

Wing: openclaw
Topic: mempalace_qdrant
Last Updated: 2026-04-24
"""

from .mcp_server import run_stdio

def main():
    run_stdio()

if __name__ == "__main__":
    main()