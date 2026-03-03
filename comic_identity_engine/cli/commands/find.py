"""Find command for Comic Identity Engine CLI.

This module provides the find command implementation for resolving
comic book identities from URLs.
"""

from comic_identity_engine.cli.main import cli_find

# Re-export for use by the commands package
find_command = cli_find
