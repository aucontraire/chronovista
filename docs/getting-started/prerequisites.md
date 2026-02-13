# Prerequisites

Everything you need before installing chronovista.

## Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| **Python** | 3.11+ (3.12 recommended) | Backend runtime |
| **Poetry** | Latest | Python dependency management |
| **Docker** | Latest (with Compose) | Development database |
| **Git** | Latest | Version control |

!!! warning "Docker is Required"
    Docker is **not optional** for development. The development database runs in a Docker container via `docker-compose.dev.yml` on port 5434. You cannot run tests or develop locally without it.

## Optional Software

| Software | Version | Purpose |
|----------|---------|---------|
| **Node.js** | 22.x LTS (or 20.x LTS) | Web frontend |
| **npm** | 10.x+ | Frontend dependency management |
| **pyenv** | Latest | Python version management |

!!! note "Node.js for Frontend"
    Node.js is only required if you want to use the web frontend. The CLI and backend API work without Node.js.

## Google Cloud Account

You need a Google Cloud account with:

- A **Google Cloud project** with the **YouTube Data API v3** enabled
- An **API key** for unauthenticated API calls
- **OAuth 2.0 credentials** (Desktop application) for authenticated access to your YouTube data

See [YouTube API Setup](youtube-api-setup.md) for a step-by-step walkthrough.

## Install Python

We recommend [pyenv](https://github.com/pyenv/pyenv) for managing Python versions.

=== "macOS"

    ```bash
    brew install pyenv
    echo 'eval "$(pyenv init -)"' >> ~/.zshrc
    source ~/.zshrc

    pyenv install 3.12.2
    pyenv local 3.12.2
    ```

=== "Linux"

    ```bash
    curl https://pyenv.run | bash
    echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.bashrc
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc
    source ~/.bashrc

    pyenv install 3.12.2
    pyenv local 3.12.2
    ```

!!! tip "Without pyenv"
    If you prefer not to use pyenv, any Python 3.11+ installation works. Just ensure `python3 --version` shows 3.11 or higher.

## Install Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH
export PATH="$HOME/.local/bin:$PATH"

# Verify
poetry --version
```

Add the PATH export to your shell profile (`~/.zshrc` or `~/.bashrc`) to make it permanent.

## Install Docker

=== "macOS"

    Download and install [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/).

=== "Linux"

    ```bash
    # Ubuntu/Debian
    sudo apt-get update
    sudo apt-get install docker-ce docker-ce-cli containerd.io docker-compose-plugin

    # Add your user to the docker group (avoids needing sudo)
    sudo usermod -aG docker $USER
    newgrp docker
    ```

Verify Docker is working:

```bash
docker --version
docker compose version
```

## Install Node.js (Optional)

Only needed for the web frontend.

=== "macOS"

    ```bash
    brew install node@22
    ```

=== "Linux (nvm)"

    ```bash
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
    source ~/.bashrc
    nvm install 22
    nvm use 22
    ```

Verify:

```bash
node --version   # Should show v22.x.x
npm --version    # Should show 10.x.x
```

## Next Steps

- [YouTube API Setup](youtube-api-setup.md) - Configure Google Cloud credentials
- [Installation](installation.md) - Install chronovista
- [Quick Start](quickstart.md) - Get running in minutes
