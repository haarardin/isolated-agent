#!/usr/bin/env bash
# Install the current OpenCode CLI release without Node.js or npm.
# The upstream installer resolves the latest release for this platform.
# Runs only inside the Dependencies image build, never on the host.
set -Eeuo pipefail

installer="$(mktemp /tmp/opencode-installer.XXXXXXXX)"
trap 'rm -f "$installer"' EXIT
curl --fail --location --silent --show-error --retry 3 \
  https://opencode.ai/v2/install -o "$installer"

# No --version argument: let the official installer select the latest release.
# --no-modify-path avoids modifying root's shell startup files in the image.
bash "$installer" --no-modify-path

test -x "$HOME/.opencode/bin/opencode" || {
  echo "ERROR: upstream OpenCode installer did not produce the CLI" >&2
  exit 1
}
install -m 0755 "$HOME/.opencode/bin/opencode" /usr/local/bin/opencode

# Test that the resulting executable works; do not parse or pin a version.
opencode --version

# Keep the installed binary, not the installer-created launcher directory.
rm -rf "$HOME/.opencode/bin"
