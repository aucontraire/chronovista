#!/bin/bash
# Development environment setup script for chronovista (Poetry-based)

set -e

echo "🚀 Setting up chronovista development environment with Poetry..."

# Check if we're in the project directory
if [ ! -f "pyproject.toml" ]; then
    echo "❌ ERROR: Must be run from the chronovista project root directory"
    exit 1
fi

# Check if Poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "📦 Poetry not found. Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    
    # Add Poetry to PATH for this session
    export PATH="$HOME/.local/bin:$PATH"
    
    echo "✅ Poetry installed successfully!"
    
    # Automatically configure PATH for common shells
    echo "🔧 Configuring PATH for Poetry..."
    
    # Detect current shell
    CURRENT_SHELL=$(basename "$SHELL")
    
    case "$CURRENT_SHELL" in
        zsh)
            SHELL_CONFIG="$HOME/.zshrc"
            ;;
        bash)
            SHELL_CONFIG="$HOME/.bashrc"
            ;;
        fish)
            SHELL_CONFIG="$HOME/.config/fish/config.fish"
            echo "🐟 Note: Fish shell detected - you may need to manually configure PATH"
            ;;
        *)
            SHELL_CONFIG="$HOME/.profile"
            echo "⚠️  Unknown shell ($CURRENT_SHELL) - using ~/.profile"
            ;;
    esac
    
    # Add PATH configuration if not already present
    PATH_EXPORT='export PATH="$HOME/.local/bin:$PATH"'
    
    if [ "$CURRENT_SHELL" = "fish" ]; then
        # Fish shell uses different syntax
        FISH_PATH='set -gx PATH $HOME/.local/bin $PATH'
        if ! grep -q "\$HOME/.local/bin" "$SHELL_CONFIG" 2>/dev/null; then
            echo "$FISH_PATH" >> "$SHELL_CONFIG"
            echo "✅ Added Poetry to PATH in $SHELL_CONFIG"
        else
            echo "ℹ️  PATH already configured in $SHELL_CONFIG"
        fi
    else
        # Bash/Zsh and other POSIX shells
        if ! grep -q "\$HOME/.local/bin" "$SHELL_CONFIG" 2>/dev/null; then
            echo "" >> "$SHELL_CONFIG"
            echo "# Added by chronovista dev_setup.sh" >> "$SHELL_CONFIG"
            echo "$PATH_EXPORT" >> "$SHELL_CONFIG"
            echo "✅ Added Poetry to PATH in $SHELL_CONFIG"
        else
            echo "ℹ️  PATH already configured in $SHELL_CONFIG"
        fi
    fi
    
    echo "💡 Note: PATH configured automatically. Restart your shell or run:"
    echo "   source $SHELL_CONFIG"
fi

# Verify Poetry is available
if ! command -v poetry &> /dev/null; then
    echo "❌ ERROR: Poetry installation failed or not in PATH"
    echo "Please install Poetry manually: https://python-poetry.org/docs/#installation"
    exit 1
fi

echo "✅ Poetry found: $(poetry --version)"

# Check if pyenv is available and set up properly
if command -v pyenv &> /dev/null; then
    echo "🐍 pyenv detected. Ensuring Python 3.11+ is available..."
    
    # Check if we have a suitable Python version
    if pyenv versions | grep -q "3.1[12]"; then
        echo "✅ Python 3.11+ found in pyenv"
    else
        echo "📦 Installing Python 3.12.2 with pyenv..."
        pyenv install 3.12.2
        pyenv local 3.12.2
    fi
fi

# Check if chronovista-env exists, create if needed
echo "🔧 Setting up chronovista-env virtual environment..."
if ! pyenv versions | grep -q "chronovista-env"; then
    echo "📦 Creating chronovista-env virtual environment..."
    pyenv virtualenv 3.12.2 chronovista-env
fi

# Configure Poetry to use chronovista-env specifically
echo "🔧 Configuring Poetry to use chronovista-env..."
poetry env use ~/.pyenv/versions/3.12.2/envs/chronovista-env/bin/python

# Install dependencies
echo "📦 Installing dependencies with Poetry..."
poetry install --with dev

# Install pre-commit hooks
echo "🔧 Setting up pre-commit hooks..."
poetry run pre-commit install

# Verify installation
echo "🔍 Verifying installation..."
poetry run python --version
poetry run pytest --version
poetry run black --version
poetry run ruff --version
poetry run mypy --version

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "🎉 You're ready to develop! Here's what you can do:"
echo ""
echo "📋 Common commands:"
echo "  make help              # Show all available commands"
echo "  make shell             # Enter Poetry shell"
echo "  make test              # Run tests"
echo "  make format            # Format code"
echo "  make lint              # Check code quality"
echo "  make quality           # Run all quality checks"
echo ""
echo "🔧 Environment management:"
echo "  make env-info          # Show environment info"
echo "  make deps-show         # Show installed packages"
echo "  poetry shell           # Enter Poetry shell manually"
echo ""
echo "📚 Documentation:"
echo "  See README.md for detailed usage instructions"
echo ""
echo "💡 Pro tip: Run 'make shell' or 'poetry shell' to activate the virtual environment!"
echo ""
echo "🛠️  If you encounter 'poetry: command not found' errors:"
echo "   1. Restart your terminal/shell"
echo "   2. Or run: source $SHELL_CONFIG"
echo "   3. Or manually run: export PATH=\"\$HOME/.local/bin:\$PATH\""
echo ""
echo "🔍 To verify Poetry is working: poetry --version"