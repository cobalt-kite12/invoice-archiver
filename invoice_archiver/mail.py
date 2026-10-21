"""从邮件中取出 PDF 附件和诺诺网链接。只要 PDF，OFD / XML / 图片一律忽略。"""
from __future__ import annotations

import email
import email.policy
import html
import re
from dataclasses import dataclass, field
from email.message import EmailMessage

from . import nuonuo
from .naming import safe_filename


@dataclass
class Attachment:
    filename: str
    data: bytes


@dataclass
class MailItem:
    message_id: str
    subject: str
    raw: bytes
    pdfs: list[Attachment] = field(default_factory=list)
    nuonuo_links: list[str] = field(default_factory=list)


def parse_message(raw: bytes) -> MailItem:
    msg: EmailMessage = email.message_from_bytes(raw, policy=email.policy.default)  # type: ignore[assignment]
    item = MailItem(message_id=str(msg.get("Message-ID", "")),
                    subject=str(msg.get("Subject", "")), raw=raw)
    texts: list[str] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        fname = part.get_filename() or ""
        is_attachment = bool(fname) or part.get_content_disposition() == "attachment"
        if is_attachment:
            data = part.get_payload(decode=True) or b""
            if fname.lower().endswith(".pdf") or ctype == "application/pdf" or data.startswith(b"%PDF-"):
                if data.startswith(b"%PDF-"):
                    item.pdfs.append(Attachment(safe_filename(fname or "附件.pdf"), data))
            continue
        if ctype in ("text/plain", "text/html"):
            try:
                texts.append(part.get_content())
            except Exception:
                texts.append((part.get_payload(decode=True) or b"").decode("utf-8", "replace"))
    body = html.unescape("\n".join(texts))
    body = re.sub(r"<[^>]+>", " ", body) + "\n" + " ".join(re.findall(r'href="([^"]+)"', "\n".join(texts)))
    item.nuonuo_links = nuonuo.find_links(body)
    return item
