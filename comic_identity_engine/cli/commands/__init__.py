"""CLI commands for Comic Identity Engine.

This package contains CLI command implementations for the Comic Identity Engine.
Commands are organized as modules and exposed through this package for use by
the CLI entry point.

Commands:
    find: Search for and resolve comic book issues from various platforms.
"""

from comic_identity_engine.cli.commands.find import find_command

__all__ = ["find_command"]
