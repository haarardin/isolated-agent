#!/usr/bin/env python3
"""Offline-safe application records, immutable source facts and DOCX/PDF rendering.

Agent-side commands use only /workspace; the host alone writes approvals.
No browser actions or external submissions occur in this program.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".atomic-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            json.dump(obj, fp, indent=2, ensure_ascii=False)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def app_dir(root, ident):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", ident):
        raise ValueError("Invalid application identifier")
    p = root / "applications" / ident
    if not p.is_dir():
        raise ValueError("Unknown application: " + ident)
    return p

def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:45] or "unknown"

def state(directory, new_status, **extra):
    path = directory / "status.json"
    obj = read_json(path)
    old = obj["status"]
    transitions = {
        "discovered": {"prepared", "manual_action_required", "failed"},
        "prepared": {"awaiting_approval", "failed", "manual_action_required"},
        "awaiting_approval": {"submitted", "failed", "manual_action_required"},
        "manual_action_required": {"awaiting_approval", "failed"},
        "failed": {"awaiting_approval"},
        "submitted": set()
    }
    if new_status not in transitions[old]:
        raise ValueError("Invalid status transition: " + old + " -> " + new_status)
    obj.update(extra)
    obj["status"] = new_status
    obj["updated_at"] = timestamp()
    write_json(path, obj)
    return obj

def new_record(root, url, company, role):
    from urllib.parse import urlparse
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        raise ValueError("A public HTTPS vacancy URL is required")
    if not company.strip() or not role.strip():
        raise ValueError("Company and role are required")
    ident = slug(company) + "-" + slug(role) + "-" + hashlib.sha256(url.encode()).hexdigest()[:10]
    target = root / "applications" / ident
    if target.exists():
        print("EXISTING " + ident + " " + read_json(target / "status.json")["status"])
        return
    target.mkdir(parents=True, exist_ok=False)
    (target / "screenshots").mkdir()
    write_json(target / "vacancy.json", {
        "company": company, "role": role, "url": url,
        "requirements": [], "description": "", "remote_eligibility": "unverified",
        "fit": "unverified", "reviewed_at": None
    })
    write_json(target / "answers.json", {})
    write_json(target / "status.json", {
        "status": "discovered", "created_at": timestamp(),
        "updated_at": timestamp(), "url": url, "company": company, "role": role,
        "submission_evidence": None
    })
    print(ident)

def choose_bullets(master, focus, requirements):
    terms = {
        "rtc": {"sip", "webrtc", "rtp", "rtcp", "sdp", "gstreamer", "media", "bfcp", "video", "sfu"},
        "backend": {"go", "backend", "architecture", "grpc", "postgresql", "redis", "microservices", "rabbitmq", "websocket"}
    }.get(focus)
    if terms is None:
        raise ValueError("Focus must be rtc or backend")
    requested = set(re.findall(r"[a-z0-9.+-]+", " ".join(requirements).lower()))
    requested -= {"with", "the", "for", "and", "our", "you", "will", "work", "experience", "years", "team"}
    selected = []
    for idx, job in enumerate(master["experience"]):
        bullets = job.get("bullets", [])
        def ranking(b):
            tags = {t.lower() for t in b.get("tags", [])}
            mentioned = set(re.findall(r"[a-z0-9.+-]+", b["text"].lower()))
            return (-(4 * len(tags & requested) +
                      2 * len(tags & terms) +
                      min(5, len(mentioned & requested))),
                    bullets.index(b))
        ranked = sorted(bullets, key=ranking)
        limit = 6 if idx == 0 else (4 if idx == 1 else 2)
        selected.append((job, ranked[:limit]))
    return selected

def setup_doc(template):
    from docx import Document
    from docx.shared import Cm, Pt
    if template.is_file():
        doc = Document(str(template))
        body = doc._element.body
        for child in list(body):
            if child.tag.split("}")[-1] != "sectPr":
                body.remove(child)
    else:
        doc = Document()
    section = doc.sections[0]
    section.top_margin = Cm(1.7)
    section.bottom_margin = Cm(1.7)
    section.left_margin = Cm(1.9)
    section.right_margin = Cm(1.9)
    st = doc.styles["Normal"]
    st.font.name = "Arial"
    st.font.size = Pt(9)
    st.paragraph_format.space_after = Pt(3)
    return doc

def para(doc, text, *, bold=False, size=None):
    from docx.shared import Pt
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    return p

def heading(doc, text):
    para(doc, text.upper(), bold=True, size=10)

def convert(docx_path, output_dir):
    cmd = ["libreoffice", "-env:UserInstallation=file:///tmp/jobapply-lo-" + str(os.getpid()),
           "--headless", "--convert-to", "pdf", "--outdir",
           str(output_dir), str(docx_path)]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    pdf = output_dir / (docx_path.stem + ".pdf")
    if res.returncode != 0 or not pdf.is_file():
        raise RuntimeError("LibreOffice conversion failed: " + res.stdout + res.stderr)
    return pdf

def validate_doc(docx_path, pdf_path, required, max_pages):
    from docx import Document
    import fitz
    doc = Document(str(docx_path))
    doc_text = "\n".join(p.text for p in doc.paragraphs)
    if not doc_text.strip():
        raise ValueError("Empty DOCX")
    with fitz.open(str(pdf_path)) as pdf:
        if not 1 <= len(pdf) <= max_pages:
            raise ValueError("Unexpected PDF page count: " + str(len(pdf)))
        text = "\n".join(page.get_text() for page in pdf)
        for needle in required:
            if needle.lower() not in text.lower() or needle.lower() not in doc_text.lower():
                raise ValueError("Missing required text in DOCX or PDF: " + needle)
        for page in pdf:
            for block in page.get_text("blocks"):
                x0, y0, x1, y1 = block[:4]
                if x0 < -2 or y0 < -2 or x1 > page.rect.width + 2 or y1 > page.rect.height + 2:
                    raise ValueError("Clipped PDF text block")
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            pix.save(str(pdf_path.parent / (pdf_path.stem + "-page-" + str(page.number + 1) + ".png")))
        doc_tokens = re.findall(r"[a-z0-9]+", doc_text.lower())
        pdf_tokens = re.findall(r"[a-z0-9]+", text.lower())
        # PDF extraction can reorder lines, but should retain nearly all DOCX words.
        from collections import Counter
        d, p = Counter(doc_tokens), Counter(pdf_tokens)
        overlap = sum((d & p).values()) / max(1, sum(d.values()))
        if overlap < 0.90:
            raise ValueError("DOCX/PDF text mismatch (" + str(round(overlap, 2)) + ")")
        return {"pages": len(pdf), "tokens_preserved": round(overlap, 3)}

def render(root, ident, focus, short_letter):
    from docx import Document
    directory = app_dir(root, ident)
    existing = read_json(directory / "status.json")
    if existing["status"] != "discovered":
        raise ValueError("Already prepared: create a fresh application/version instead of overwriting")
    master = read_json(root / "candidate/master-resume.json")
    profile = read_json(root / "candidate/profile.json")
    vacancy = read_json(directory / "vacancy.json")
    if vacancy["url"] != existing["url"]:
        raise ValueError("Vacancy URL changed")
    if not vacancy.get("requirements") or not vacancy.get("reviewed_at"):
        raise ValueError("Vacancy requirements must first be verified from the live posting")
    if not master.get("experience") or not master.get("skills") or not profile.get("name"):
        raise ValueError("Master resume/profile incomplete. Import your private candidate data")
    contact = profile.get("contact", {})
    if not contact.get("email"):
        raise ValueError("Missing contact.email")
    selected = choose_bullets(master, focus, vacancy['requirements'])
    tpl = root / "candidate/master-resume.docx"
    doc = setup_doc(tpl)
    para(doc, profile["name"], bold=True, size=15)
    para(doc, master.get("headline", "Senior Backend Engineer"), bold=True, size=10)
    contact_values = [profile.get("location", ""), contact.get("email", ""),
                      contact.get("phone", ""), contact.get("linkedin", ""), contact.get("github", "")]
    para(doc, " | ".join(str(v) for v in contact_values if v))
    heading(doc, "Professional Summary")
    para(doc, master.get("summary", ""))
    heading(doc, "Technical Skills")
    categories = list(master["skills"].items())
    categories.sort(key=lambda pair: (0 if (focus == "rtc" and ("SIP" in pair[0] or "Media" in pair[0]))
                                        or (focus == "backend" and ("Backend" in pair[0] or "Database" in pair[0])) else 1))
    for category, values in categories:
        para(doc, category + ": " + ", ".join(values))
    heading(doc, "Professional Experience")
    for job, bullets in selected:
        para(doc, job["company"] + " | " + job["title"] + " | " + job["dates"], bold=True)
        if job.get("project"):
            para(doc, job["project"])
        for bullet in bullets:
            para(doc, "• " + bullet["text"])
    if master.get("education"):
        heading(doc, "Education")
        for item in master["education"]:
            para(doc, item)
    if master.get("languages"):
        heading(doc, "Languages")
        para(doc, ", ".join(master["languages"]))
    rpath = directory / "resume.docx"
    doc.save(str(rpath))
    convert(rpath, directory)
    # Only user-confirmed experience statements are used in the letter.
    letter = setup_doc(root / "candidate/master-cover-letter.docx")
    para(letter, profile["name"], bold=True, size=14)
    para(letter, " | ".join(str(v) for v in [contact.get("email"), contact.get("linkedin")] if v))
    para(letter, "Dear Hiring Team,")
    para(letter, "I am applying for the " + vacancy["role"] + " position at " + vacancy["company"] +
         ". My background combines hands-on Go backend engineering with real-time communications and distributed systems.")
    highlights = []
    for job, bullets in selected[:2]:
        if bullets:
            highlights.append(bullets[0]["text"])
    if highlights:
        para(letter, "At " + selected[0][0]["company"] + ", I " +
             highlights[0][0].lower() + highlights[0][1:].rstrip(".") + ".")
    if len(highlights) > 1 and not short_letter:
        para(letter, "At " + selected[1][0]["company"] + ", I also " +
             highlights[1][0].lower() + highlights[1][1:].rstrip(".") + ".")
    para(letter, "I would welcome a conversation about the engineering challenges of this role.")
    para(letter, "Kind regards,")
    para(letter, profile["name"])
    lpath = directory / "cover-letter.docx"
    letter.save(str(lpath))
    convert(lpath, directory)
    (directory / "cover-letter.txt").write_text("\n\n".join(p.text for p in letter.paragraphs) + "\n", encoding="utf-8")
    qa = {
        "resume": validate_doc(rpath, directory / "resume.pdf", [profile["name"], "Professional Experience"], 5),
        "cover_letter": validate_doc(lpath, directory / "cover-letter.pdf", [profile["name"], vacancy["role"]], 2),
        "focus": focus, "validated_at": timestamp(),
        "source_ids": [b["id"] for _, bullets in selected for b in bullets],
    }
    write_json(directory / "quality.json", qa)
    state(directory, "prepared", resume="resume.pdf", cover_letter="cover-letter.pdf", quality=qa)
    state(directory, "awaiting_approval")
    print("PREPARED " + ident + " (approval required)\n" + json.dumps(qa, indent=2))

def artifact_digest(directory):
    # Bind permission to every candidate-facing answer and submitted file.
    st = read_json(directory / "status.json")
    h = hashlib.sha256(st["url"].encode())
    for name in ("resume.pdf", "cover-letter.pdf", "cover-letter.txt",
                 "answers.json", "vacancy.json"):
        path = directory / name
        if not path.is_file():
            raise ValueError("Missing approval artifact: " + name)
        h.update(name.encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def audit(root, ident, refresh=False):
    from docx import Document
    directory = app_dir(root, ident)
    st = read_json(directory / "status.json")
    if st["status"] not in ("prepared", "awaiting_approval", "manual_action_required", "failed"):
        raise ValueError("Only an existing unsubmitted application can be audited")
    master = read_json(root / "candidate/master-resume.json")
    profile = read_json(root / "candidate/profile.json")
    allowed = {b["text"] for job in master["experience"] for b in job.get("bullets", [])}
    doc = Document(str(directory / "resume.docx"))
    for p in doc.paragraphs:
        line = p.text.strip()
        if line.startswith("•") and line.lstrip("•").strip() not in allowed:
            raise ValueError("Resume bullet not present in immutable master: " + line[:90])
    if refresh:
        if (root / "approvals" / (ident + ".json")).exists():
            raise ValueError("Already approved. Revoke the host approval before editing documents.")
        with tempfile.TemporaryDirectory(prefix=".build-", dir=directory) as temp:
            dest = Path(temp)
            for kind in ("resume", "cover-letter"):
                source = directory / (kind + ".docx")
                fresh = convert(source, dest)
                os.replace(fresh, directory / (kind + ".pdf"))
        letter = Document(str(directory / "cover-letter.docx"))
        (directory / "cover-letter.txt").write_text(
            "\n\n".join(p.text for p in letter.paragraphs) + "\n", encoding="utf-8")
    vacancy = read_json(directory / "vacancy.json")
    result = {
        "resume": validate_doc(directory / "resume.docx", directory / "resume.pdf",
                               [profile["name"], "Professional Experience"], 5),
        "cover_letter": validate_doc(directory / "cover-letter.docx", directory / "cover-letter.pdf",
                                    [profile["name"], vacancy["role"]], 2),
        "audited_at": timestamp()
    }
    write_json(directory / "quality.json", result)
    print("AUDIT OK " + ident + "\n" + json.dumps(result, indent=2))

def block(root, ident, status_value, reason):
    if status_value not in ("failed", "manual_action_required") or not reason.strip():
        raise ValueError("Use failed/manual_action_required and a nonempty reason")
    directory = app_dir(root, ident)
    state(directory, status_value, error_reason=reason)
    print("BLOCKED " + ident + ": " + reason)

def resume(root, ident):
    directory = app_dir(root, ident)
    obj = read_json(directory / "status.json")
    if obj["status"] not in ("failed", "manual_action_required"):
        raise ValueError("Not a resumable paused application")
    state(directory, "awaiting_approval", error_reason=None)
    print("RESUMED " + ident + " (approval still required)")

def approve(root, ident):
    directory = app_dir(root, ident)
    obj = read_json(directory / "status.json")
    if obj["status"] != "awaiting_approval":
        raise ValueError("Application must await approval")
    approval = root / "approvals" / (ident + ".json")
    if approval.exists():
        raise ValueError("Approval exists; review or revoke it explicitly")
    write_json(approval, {"application": ident, "url": obj["url"],
                          "artifact_digest": artifact_digest(directory),
                          "approved_at": timestamp(), "single_use": True})
    os.chmod(approval, 0o600)
    print("APPROVED " + ident + " (single use, only matching document hashes)")

def check_approval(root, ident):
    """Validate current user authorization BEFORE final browser submission."""
    directory = app_dir(root, ident)
    st = read_json(directory / "status.json")
    if st["status"] != "awaiting_approval":
        raise ValueError("Application is not awaiting approval")
    path = root / "approvals" / (ident + ".json")
    if not path.is_file():
        raise ValueError("Missing host-side approval")
    approval = read_json(path)
    if (approval.get("application") != ident
            or approval.get("url") != st["url"]
            or approval.get("artifact_digest") != artifact_digest(directory)):
        raise ValueError("Approval does not match current vacancy or documents/answers")
    print("APPROVAL VERIFIED", ident)

def submitted(root, ident, evidence):
    directory = app_dir(root, ident)
    obj = read_json(directory / "status.json")
    if obj["status"] != "awaiting_approval":
        raise ValueError("Application cannot be submitted in status " + obj["status"])
    approval = root / "approvals" / (ident + ".json")
    if not approval.is_file():
        raise ValueError("Host approval is missing; do not submit")
    permission = read_json(approval)
    if permission["application"] != ident or permission["url"] != obj["url"] or permission["artifact_digest"] != artifact_digest(directory):
        raise ValueError("Approval does not match job/documents")
    if not evidence.strip():
        raise ValueError("Submission confirmation evidence required")
    state(directory, "submitted", submitted_at=timestamp(), submission_evidence=evidence)
    print("RECORDED SUBMITTED " + ident)
    # Never automatically delete the approval: keep audit trail.

def smoke(root):
    from docx import Document
    import fitz
    dest = root / "applications" / "__smoke__"
    dest.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_heading("Test Resume", 0)
    doc.add_paragraph("This is a smoke-test paragraph.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Skill"
    table.cell(0, 1).text = "Experience"
    table.cell(1, 0).text = "Go"
    table.cell(1, 1).text = "Test"
    docx = dest / "smoke.docx"
    doc.save(str(docx))
    verify = Document(str(docx))
    assert len(verify.tables) == 1 and "Test Resume" in verify.paragraphs[0].text
    pdf = convert(docx, dest)
    with fitz.open(pdf) as obj:
        assert len(obj) >= 1 and "Test Resume" in obj[0].get_text()
        obj[0].get_pixmap().save(str(dest / "smoke-preview.png"))
    print("DOCX/PDF SMOKE OK:", dest)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/workspace"))
    sub = parser.add_subparsers(dest="cmd", required=True)
    new = sub.add_parser("new")
    for k in ("url", "company", "role"):
        new.add_argument("--" + k, required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("id")
    prep.add_argument("--focus", choices=("rtc", "backend"), default="rtc")
    prep.add_argument("--short-letter", action="store_true")
    for name in ("approve", "status", "check-approval"):
        p = sub.add_parser(name)
        p.add_argument("id")
    done = sub.add_parser("submitted")
    done.add_argument("id")
    done.add_argument("--evidence", required=True)
    sub.add_parser("smoke")
    for name in ("audit", "rebuild", "resume"):
        p = sub.add_parser(name)
        p.add_argument("id")
    pause = sub.add_parser("block")
    pause.add_argument("id")
    pause.add_argument("--status", choices=("failed", "manual_action_required"), required=True)
    pause.add_argument("--reason", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.cmd == "new": new_record(root, args.url, args.company, args.role)
    elif args.cmd == "prepare": render(root, args.id, args.focus, args.short_letter)
    elif args.cmd == "approve": approve(root, args.id)
    elif args.cmd == "submitted": submitted(root, args.id, args.evidence)
    elif args.cmd == "check-approval": check_approval(root, args.id)
    elif args.cmd == "status": print(json.dumps(read_json(app_dir(root, args.id) / "status.json"), indent=2))
    elif args.cmd == "smoke": smoke(root)
    elif args.cmd == "audit": audit(root, args.id)
    elif args.cmd == "rebuild": audit(root, args.id, refresh=True)
    elif args.cmd == "resume": resume(root, args.id)
    elif args.cmd == "block": block(root, args.id, args.status, args.reason)

if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, RuntimeError) as ex:
        print("ERROR:", ex, file=sys.stderr)
        sys.exit(2)
