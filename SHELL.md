# Shell Configuration for Comic Identity Engine

Quick setup for working with the Comic Identity Engine in your shell.

## Quick Setup (Zsh)

Add this to your `~/.zshrc`:

```bash
# Comic Identity Engine
source /mnt/extra/josh/code/comic-identity-engine/.zshrc.local
```

Then reload your shell:
```bash
source ~/.zshrc
```

## Quick Setup (Bash)

Add this to your `~/.bashrc`:

```bash
# Comic Identity Engine
source /mnt/extra/josh/code/comic-identity-engine/.bashrc.local
```

Then reload your shell:
```bash
source ~/.bashrc
```

## What You Get

### Aliases
- `pytest` → `uv run pytest` (runs tests in project environment)
- `py` → `uv run python` (runs Python in project environment)
- `cie` → `cd` to project root

### Helper Functions
- `cie-test` → Run tests (e.g., `cie-test tests/test_parsing.py -v`)
- `cie-run` → Run a Python script (e.g., `cie-run script.py`)
- `cie-repl` → Start Python REPL with project dependencies
- `cie-status` → Show project status

### Direnv Integration

If you have [direnv](https://direnv.net) installed, the `.envrc` file will automatically load the project environment when you `cd` into the project.

**Install direnv:**
```bash
# macOS
brew install direnv

# Ubuntu/Debian
sudo apt install direnv

# Arch
sudo pacman -S direnv
```

**Setup direnv hook (one-time):**
```bash
# For Zsh (add to ~/.zshrc)
eval "$(direnv hook zsh)"

# For Bash (add to ~/.bashrc)
eval "$(direnv hook bash)"
```

## Usage Examples

```bash
# Jump to project
cie

# Run all tests
pytest

# Run specific test
pytest tests/test_parsing.py::test_negative_issue_with_hash -v

# Run a Python script
py examples/some_script.py

# Start REPL
py

# Check status
cie-status
```

## Troubleshooting

### "command not found: uv"
You need to install `uv`:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### "command not found: direnv" (optional)
Install direnv or remove the direnv hook from the shell config.

### Environment not loading
Make sure you've run `uv sync` at least once to create the `.venv`.
