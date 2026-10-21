from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

from invoice_archiver.config import Config


def make_eml(subject: str, attachments: list[tuple[str, bytes]] = (), body: str = "见附件",
             html: str | None = None, msgid: str | None = None) -> bytes:
    m = EmailMessage()
    m["From"] = "sender@example.com"
    m["To"] = "inbox@example.com"
    m["Subject"] = subject
    m["Message-ID"] = msgid or f"<{abs(hash((subject, len(attachments), body)))}@example.com>"
    m.set_content(body)
    if html:
        m.add_alternative(html, subtype="html")
    for name, data in attachments:
        maintype, subtype = {
            ".pdf": ("application", "pdf"), ".ofd": ("application", "ofd"),
            ".xml": ("text", "xml"),
        }[Path(name).suffix]
        m.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return m.as_bytes()


def make_config(tmp: Path, **archive) -> Config:
    cfg = Config()
    cfg.archive.output_dir = tmp / "archive"
    for k, v in archive.items():
        setattr(cfg.archive, k, v)
    return cfg
