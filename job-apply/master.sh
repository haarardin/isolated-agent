#!/usr/bin/env bash
# Host-controlled staging and promotion of the master resume (never agent-automatic).
set -euo pipefail
APP="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$APP/state"
SOURCE="$ROOT/candidate"
DRAFTS="$ROOT/applications/master-drafts"
umask 077
fail() { echo "ERROR: $*" >&2; exit 2; }

case "${1:-}" in
  start)
    [[ -f "$SOURCE/master-resume.json" && -f "$SOURCE/master-resume.docx" ]] || fail "Import candidate master JSON and DOCX first"
    mkdir -p "$DRAFTS"
    name="draft-$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import secrets;print(secrets.token_hex(3))')"
    dir="$DRAFTS/$name"
    mkdir -m 700 "$dir"
    cp "$SOURCE/master-resume.json" "$SOURCE/master-resume.docx" "$dir/"
    (cd "$SOURCE" && sha256sum master-resume.json master-resume.docx) > "$dir/original.sha256"
    printf '%s\n' "$name"
    echo "Agent may edit /workspace/applications/master-drafts/$name"
    echo "Original remains read-only; promotion requires host confirmation."
    ;;
  promote)
    name="${2:-}"
    [[ "$name" =~ ^draft-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{6}$ ]] || fail "Invalid draft id"
    dir="$DRAFTS/$name"
    [[ -f "$dir/original.sha256" && -f "$dir/master-resume.docx" && -f "$dir/master-resume.json" ]] || fail "Incomplete draft"
    # Reject changes to the source after the draft was made.
    (cd "$SOURCE" && sha256sum -c "$dir/original.sha256") || fail "Master changed since draft creation"
    python3 -m json.tool "$dir/master-resume.json" >/dev/null
    # Validate Word package with the real document environment.
    (cd "$APP"; podman-compose -f compose.yaml exec -T agent \
      python3 -c 'from docx import Document;d=Document("/workspace/applications/master-drafts/'"$name"'/master-resume.docx");assert len(d.paragraphs)>0')
    echo "You are replacing the authoritative master JSON + DOCX. Review the draft first."
    [[ -t 0 ]] || fail "Interactive terminal required for master promotion"
    read -r -p "Type PROMOTE to create a backup and replace the master: " reply
    [[ "$reply" == PROMOTE ]] || fail "Cancelled"
    backup="$SOURCE/backups/$(date -u +%Y%m%dT%H%M%SZ)-$name"
    mkdir -p "$backup"
    cp "$SOURCE/master-resume.json" "$SOURCE/master-resume.docx" "$backup/"
    # Stage first, then atomically rename each file. Backup remains recoverable.
    cp "$dir/master-resume.json" "$SOURCE/.master-resume.json.new"
    cp "$dir/master-resume.docx" "$SOURCE/.master-resume.docx.new"
    mv -f "$SOURCE/.master-resume.json.new" "$SOURCE/master-resume.json"
    mv -f "$SOURCE/.master-resume.docx.new" "$SOURCE/master-resume.docx"
    chmod 600 "$SOURCE/master-resume."{json,docx}
    echo "Promoted; previous masters backed up to $backup"
    ;;
  *) cat <<'HELP'
Host-only master resume operations:
  ./job-apply/master.sh start
  # Ask Codex to edit files in /workspace/applications/master-drafts/<id>
  ./job-apply/master.sh promote <draft-id>  # interactive, creates backups
HELP
     ;;
esac
