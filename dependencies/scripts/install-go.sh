#!/usr/bin/env bash
# Only run at image build time; optionally pass a verified SHA256 as arg 2.
set -Eeuo pipefail
version="${1:?Go version required}"
case "$version" in *[!0-9.]*|'') echo "Invalid Go version" >&2; exit 2;; esac
case "$(dpkg --print-architecture)" in
  amd64) arch=amd64;;
  arm64) arch=arm64;;
  *) echo "Unsupported CPU architecture" >&2; exit 2;;
esac
file="go${version}.linux-${arch}.tar.gz"
curl -fLsS --retry 3 "https://go.dev/dl/${file}" -o /tmp/go.tar.gz
if [[ -n "${2:-}" ]]; then
  printf '%s  %s\n' "$2" /tmp/go.tar.gz | sha256sum -c -
fi
tar -C /usr/local -xzf /tmp/go.tar.gz
ln -s /usr/local/go/bin/go /usr/local/bin/go
ln -s /usr/local/go/bin/gofmt /usr/local/bin/gofmt
rm -f /tmp/go.tar.gz
