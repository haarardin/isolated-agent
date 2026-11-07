#!/usr/bin/env bash
set -Eeuo pipefail
version="${1:?Node version required}"
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || exit 2
case "$(dpkg --print-architecture)" in
  amd64) arch=x64 ;;
  arm64) arch=arm64 ;;
  *) echo "Unsupported Node architecture" >&2; exit 2 ;;
esac
file="node-v${version}-linux-${arch}.tar.xz"
base="https://nodejs.org/dist/v${version}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fLsS --retry 3 "$base/$file" -o "$tmp/$file"
curl -fLsS --retry 3 "$base/SHASUMS256.txt" -o "$tmp/SHASUMS256.txt"
(cd "$tmp"; grep -F "  $file" SHASUMS256.txt | sha256sum -c -)
mkdir -p "/opt/node-v${version}"
tar -xJf "$tmp/$file" --strip-components=1 -C "/opt/node-v${version}"
for bin in node npm npx corepack; do ln -s "/opt/node-v${version}/bin/$bin" "/usr/local/bin/$bin"; done
node --version
npm --version
