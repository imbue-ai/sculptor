#!/usr/bin/env bash
set -euo pipefail

echo "WARNING: This script will install Homebrew for x86_64 and some packages."
echo "You only need this if you are on an Apple Silicon Mac and need to build x86_64 binaries."
echo "If you proceed, you will end up with two Homebrew installations:"
echo "  /usr/local/bin/brew (x86_64)"
echo "  /opt/homebrew/bin/brew (arm64)"
echo "You run a non-zero chance of inconveniencing your own system."

# Only prompt the user if running in an interactive terminal
if [[ -t 0 ]]; then
    read -p "Do you want to proceed? (y/n) " answer
    if [[ "$answer" != "y" ]]; then
        echo "Aborting."
        exit 1
    fi
fi

softwareupdate --install-rosetta --agree-to-license || {
  echo "Rosetta is already installed."
}


unset HOMEBREW_PREFIX HOMEBREW_CELLAR HOMEBREW_REPOSITORY
# It's very important that this is /bin/bash and not your free-floating bash that might have been installed by homebrew.
# The brew bash will NOT codeswitch into x86_64.
# Also, defense in depth guard to prevent deleting the original homebrew.
sudo chflags -R uchg /opt/homebrew
/usr/bin/arch -x86_64 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# You can delete the real homebrew again.
sudo chflags -R nouchg /opt/homebrew # unlock after

# Let's start a multiline echo string
cat <<'EOF'
You will want to add something like this to your bashrc
# Set up Homebrew depending on the architecture.
if [ "$(uname -s)" = "Darwin" ]; then
  # choose the correct Homebrew by architecture
  if [ "$(uname -m)" = "arm64" ]; then
    [ -x /opt/homebrew/bin/brew ] && eval "$(/opt/homebrew/bin/brew shellenv)"
  else
    [ -x /usr/local/bin/brew ] && eval "$(/usr/local/bin/brew shellenv)"
  fi

  # keep stray HOMEBREW_* from breaking things
  unset HOMEBREW_PREFIX HOMEBREW_CELLAR HOMEBREW_REPOSITORY 2>/dev/null || true
fi
EOF

echo "Now bootstrapping x86_64 Homebrew packages under Rosetta..."

# Run all brew installs under Rosetta with a clean x86_64 environment
arch -x86_64 /usr/local/bin/brew install bash
arch -x86_64 /usr/local/bin/brew install uv nvm just tmux

# Install an Intel build of Python (example: 3.11)
arch -x86_64 /usr/local/bin/uv python install cpython-3.11.13-macos-x86_64-none
arch -arm64 /opt/homebrew/bin/uv python install cpython-3.11.13-macos-aarch64-none


# Ensure nvm setup happens in x86_64 context too
arch -x86_64 /usr/local/bin/bash -c '
  source /usr/local/opt/nvm/nvm.sh
  nvm install 20.13.1
  nvm alias electron-x64 20.13.1
'

echo "Build Dependencies for Intel Mac successfully installed"
