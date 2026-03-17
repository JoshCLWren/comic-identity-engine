# Shell Configuration for Comic Identity Engine
## ⚠️ MANDATORY: Fix Broken Code

**ALL AI AGENTS MUST READ THIS:**

When you encounter broken code, tests, or functionality in this codebase, **you are REQUIRED to fix it**. Do NOT ignore broken code. Do NOT work around it. Do NOT leave it for "later".

**If you find it, you fix it.**

This includes but is not limited to:
- Failing tests
- Syntax errors
- Import errors
- Type errors
- Logic bugs
- LSP warnings that indicate real problems
- Inconsistent behavior

**No exceptions. No excuses.**

---


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
- `pytest` → project `.venv/bin/pytest`
- `py` → project `.venv/bin/python`
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
Run `uv sync` once from the project root, then re-enter the directory so direnv can attach the local `.venv`.
