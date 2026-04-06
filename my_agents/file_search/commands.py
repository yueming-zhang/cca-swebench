# pyre-strict
from __future__ import annotations

from typing import Dict


def get_allowed_commands() -> Dict[str, str]:
    """Return mapping of allowed commands for the file search agent.

    Focuses on search, read, and navigation commands.
    Write operations are limited by the file access policy to /tmp only.
    """
    return {
        # File search commands
        "find": "Search for files in a directory hierarchy by name, type, size, date, etc.",
        "locate": "Find files by name using a pre-built database (if available)",
        # Content search commands
        "grep": "Search for text patterns in files (supports regex with -E/-P)",
        "rg": "ripgrep - fast recursive search (if available)",
        # File reading
        "cat": "Print file contents",
        "head": "Show first lines of a file",
        "tail": "Show last lines of a file",
        "less": "View file contents page by page",
        # File info
        "ls": "List directory contents",
        "pwd": "Print current working directory",
        "wc": "Count lines/words/bytes in files",
        "stat": "Display file or file system status",
        "file": "Determine file type",
        "du": "Estimate file space usage",
        "tree": "Display directory tree structure (if available)",
        # Text processing (for filtering results)
        "sort": "Sort lines of text",
        "uniq": "Report or omit repeated lines",
        "cut": "Remove sections from each line",
        "awk": "Text processing and data extraction",
        "sed": "Stream editor for filtering and transforming text",
        "xargs": "Build and execute command lines from standard input",
        "tr": "Translate or delete characters",
        # Write to /tmp only (enforced by policy)
        "tee": "Read from stdin and write to stdout and files",
        "cp": "Copy files (writes restricted to /tmp by policy)",
        "mkdir": "Create directories (restricted to /tmp by policy)",
        "touch": "Create empty files (restricted to /tmp by policy)",
        # Utility
        "echo": "Display text or write to files",
        "python3": "Run Python scripts for advanced search operations",
    }
