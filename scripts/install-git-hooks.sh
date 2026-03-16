#!/bin/bash
# Install pre-commit hook for Comic Identity Engine

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_SOURCE="$SCRIPT_DIR/../.git/hooks/pre-commit"
HOOK_TARGET="$SCRIPT_DIR/../.git/hooks/pre-commit"

echo "Installing pre-commit hook..."

# Copy the hook if it doesn't exist or is different
if [ ! -f "$HOOK_TARGET" ] || ! cmp -s "$HOOK_SOURCE" "$HOOK_TARGET"; then
    cp "$HOOK_SOURCE" "$HOOK_TARGET"
    chmod +x "$HOOK_TARGET"
    echo "✓ Pre-commit hook installed"
else
    echo "✓ Pre-commit hook already installed (up to date)"
fi

echo ""
echo "The pre-commit hook will now:"
echo "  • Block commits with type/linter ignores"
echo "  • Run linting on staged files"
echo "  • Check for Any types"
echo "  • Verify code formatting"
echo ""
echo "To test manually: bash scripts/lint.sh --staged"
