#!/bin/bash

# Claude Code Cost Calculator Installation Script
# Automatically detects the best installation method for your system

set -e

echo "🚀 Installing Claude Code Cost Calculator..."

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Try uv first (recommended - modern and fast)
if command_exists uv; then
    echo "✅ Using uv tool (recommended - modern & fast)"
    uv tool install claude-code-cost
    echo "✨ Installation complete! Run 'ccc' to get started."
    exit 0
fi

# Try pipx second (traditional but reliable)
if command_exists pipx; then
    echo "✅ Using pipx (traditional alternative)"
    pipx install claude-code-cost
    echo "✨ Installation complete! Run 'ccc' to get started."
    exit 0
fi

# Try to install uv first (preferred)
echo "📦 Installing uv (recommended modern tool)..."
if curl -LsSf https://astral.sh/uv/install.sh | sh; then
    # Source the shell to get uv in PATH
    export PATH="$HOME/.cargo/bin:$PATH"
    if command_exists uv; then
        uv tool install claude-cost
        echo "✨ Installation complete! Run 'ccc' to get started."
        echo "💡 Note: You may need to restart your terminal or run: source ~/.bashrc"
        exit 0
    fi
fi

# Try to install pipx as fallback
if command_exists brew; then
    echo "📦 Installing pipx via Homebrew as fallback..."
    brew install pipx
    pipx install claude-code-cost
    echo "✨ Installation complete! Run 'ccc' to get started."
    exit 0
fi

# Fallback to pip with user install
if command_exists pip; then
    echo "⚠️  Using pip --user as fallback method"
    echo "   Note: You may need to add ~/.local/bin to your PATH"
    pip install --user claude-code-cost
    
    # Add to PATH instruction
    echo ""
    echo "📝 To use claude-cost from anywhere, add this to your shell profile:"
    echo "   export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
    echo "   Then restart your terminal or run: source ~/.zshrc"
    echo "✨ Installation complete!"
    exit 0
fi

# If nothing works
echo "❌ Could not find pip, uv, pipx, or brew on your system."
echo "   Please install Python and pip first, then run:"
echo "   pip install claude-code-cost"
exit 1