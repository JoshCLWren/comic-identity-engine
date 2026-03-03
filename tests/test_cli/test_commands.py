"""Tests for CLI commands package."""


class TestCommandsModule:
    """Tests for CLI commands module imports."""

    def test_find_command_import(self) -> None:
        """Test that find_command can be imported from commands module."""
        from comic_identity_engine.cli.commands import find_command

        # Verify it's the same as cli_find from main
        from comic_identity_engine.cli.main import cli_find

        assert find_command is cli_find

    def test_find_module_exports(self) -> None:
        """Test that find module exports find_command."""
        from comic_identity_engine.cli.commands.find import find_command
        from comic_identity_engine.cli.main import cli_find

        assert find_command is cli_find

    def test_commands_all_exports(self) -> None:
        """Test that commands module __all__ is correct."""
        from comic_identity_engine.cli import commands

        assert hasattr(commands, "__all__")
        assert "find_command" in commands.__all__

    def test_find_module_imports_main(self) -> None:
        """Test that find module properly imports from main."""
        from comic_identity_engine.cli.commands import find

        # Verify cli_find is imported
        assert hasattr(find, "cli_find")
        assert hasattr(find, "find_command")
        assert find.find_command is find.cli_find
