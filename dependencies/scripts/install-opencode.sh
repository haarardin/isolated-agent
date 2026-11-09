#!/usr/bin/env bash
# Install the native OpenCode V2 binary; DO NOT pull Node.js or npm.
# The official V2 bootstrap downloads the architecture-specific CLI archive.
# Runs inside the Dependencies image build only, never on the host.
set -Eeuo pipefail

version="${1:-2.0.0}"
[[ "$version" =~ ^2\.[0-9]+\.[0-9]+$ ]] || {
  echo "ERROR: expected a pinned OpenCode V2 release (e.g. 2.0.0)" >&2
  exit 2
}

installer="$(mktemp /tmp/opencode-installer.XXXXXXXX)"
trap 'rm -f "$installer"' EXIT
curl --fail --location --silent --show-error --retry 3 \
  https://opencode.ai/v2/install -o "$installer"

# The upstream script takes --version, --no-modify-path and writes a native
# executable to $HOME/.opencode/bin. No Node/npm runtime is installed.
bash "$installer" --version "$version" --no-modify-path

test -x "$HOME/.opencode/bin/opencode" || {
  echo "ERROR: upstream OpenCode installer did not produce the CLI" >&2
  exit 1
}
install -m 0755 "$HOME/.opencode/bin/opencode" /usr/local/bin/opencode
actual="$(opencode --version)"
[[ "$actual" == "$version" || "$actual" == "v$version" ]] || {
  echo "ERROR: expected OpenCode $version, got $actual" >&2
  exit 1
}
# Keep only the selected binary, not install-time launcher files.
rm -rf "$HOME/.opencode/bin"
