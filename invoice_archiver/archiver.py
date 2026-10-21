"""核心流程：一封邮件 → 若干 PDF → 解析 → 命名 → 按月归档 → 写台账。"""
from __future__ import annotations

import csv
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from . import nuonuo
from .config import Config
from .ledger import Ledger
from .mail import Attachment, MailItem, parse_message
from .naming import base_stem, companion_name, period_of, unique_stem
from .parse import INVOICE, ParsedDoc, parse_pdf

Fetcher = Callable[[str], bytes]


@dataclass
class Result:
    filed: list[Path] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    skipped_message: bool = False


class Archiver:
    def __init__(self, cfg: Config, fetcher: Fetcher | None = None, dry_run: bool = False):
        self.cfg = cfg
        self.dry_run = dry_run
        self.fetcher = fetcher or (lambda url: nuonuo.fetch_pdf(
            url, timeout=cfg.nuonuo.timeout, retries=cfg.nuonuo.retries))
        self.ledger = Ledger(cfg.ledger_path)

    # ------------------------------------------------------------------
    def process_raw(self, raw: bytes) -> Result:
        return self.process(parse_message(raw))

    def process(self, mail: MailItem) -> Result:
        res = Result()
        key = Ledger.message_key(mail.message_id, mail.raw)
        if self.ledger.message_seen(key):
            res.skipped_message = True
            return res

        pdfs = list(mail.pdfs)
        if not pdfs and mail.nuonuo_links and self.cfg.nuonuo.enabled:
            for link in mail.nuonuo_links:
                try:
                    pdfs.append(Attachment("诺诺发票.pdf", self.fetcher(link)))
                except Exception as e:
                    res.failures.append(f"诺诺链接下载失败：{e}")
        if not pdfs:
            if res.failures:  # 诺诺下载失败：不标记已处理，下次自动重试
                self._record_failures(mail, res, [])
                return res
            if "发票" in mail.subject:
                res.failures.append("主题像发票邮件，但没有 PDF 附件或可识别的发票链接")
                self._record_failures(mail, res, [])
            else:  # 普通邮件（不是发票），静默跳过
                res.skipped_message = True
            if not self.dry_run:
                self.ledger.mark_message(key)
            return res

        with tempfile.TemporaryDirectory(prefix="invoice-") as tmp:
            docs: list[tuple[Attachment, Path, ParsedDoc]] = []
            for i, att in enumerate(pdfs):
                p = Path(tmp) / f"{i}.pdf"
                p.write_bytes(att.data)
                try:
                    docs.append((att, p, parse_pdf(p, self.cfg.item_aliases)))
                except Exception as e:
                    res.failures.append(f"{att.filename}：PDF 解析失败（{type(e).__name__}）")
            self._file_docs(mail, docs, res)
            if res.failures:
                self._record_failures(mail, res, [a for a, _, d in docs
                                                  if d.kind != INVOICE or d.missing()])

        if not res.failures and not self.dry_run:
            self.ledger.mark_message(key)
        return res

    # ------------------------------------------------------------------
    def _file_docs(self, mail: MailItem, docs, res: Result) -> None:
        invoices = [(a, p, d) for a, p, d in docs if d.kind == INVOICE]
        companions = [(a, p, d) for a, p, d in docs if d.kind not in (INVOICE, "未知")]
        for a, _, d in docs:
            if d.kind == "未知":
                res.failures.append(f"{a.filename}：认不出是发票还是附属单据")
        if not invoices:
            res.failures.append("没有找到发票 PDF")
            return

        for att, path, doc in invoices:
            miss = doc.missing()
            if miss:
                res.failures.append(f"{att.filename}：读不出 {'、'.join(miss)}")
                continue
            if self.ledger.has_invoice(doc.invoice_no):
                res.duplicates.append(doc.invoice_no)
                continue
            period = period_of(doc.issue_date, self.cfg.archive.cycle_start_day)
            folder = self.cfg.archive.output_dir / period
            stem = unique_stem(
                base_stem(doc.item, doc.amount, doc.issue_date),
                lambda s: (folder / f"{s}.pdf").exists() or self.ledger.name_taken(period, s))

            mine = self._match_companions(doc, invoices, companions)
            extra_names: list[str] = []
            if not self.dry_run:
                folder.mkdir(parents=True, exist_ok=True)
                self._write(path, folder / f"{stem}.pdf", period)
            res.filed.append(folder / f"{stem}.pdf")
            for _, cpath, cdoc in mine:
                cname = companion_name(stem, cdoc.kind)
                if cname in extra_names:  # 同类附属单据有多份
                    cname = companion_name(f"{stem}-{len(extra_names) + 1}", cdoc.kind)
                extra_names.append(cname)
                if not self.dry_run:
                    self._write(cpath, folder / cname, period)
                res.filed.append(folder / cname)
            if not self.dry_run:
                self.ledger.add({
                    "开票日期": doc.issue_date.isoformat(), "项目": doc.item,
                    "金额": f"{doc.amount:.2f}", "销售方": doc.seller or "",
                    "发票号": doc.invoice_no, "文件名": f"{stem}.pdf",
                    "附带文件": ";".join(extra_names), "归档目录": period,
                    "来源邮件主题": mail.subject[:120],
                })

    @staticmethod
    def _match_companions(doc: ParsedDoc, invoices, companions):
        if len(invoices) == 1:
            return companions
        # 一封邮件多张发票：按发票号、再按金额配对附属单据
        out = [c for c in companions if c[2].invoice_no and c[2].invoice_no == doc.invoice_no]
        if not out:
            out = [c for c in companions if c[2].amount is not None and c[2].amount == doc.amount]
        return out

    def _write(self, src: Path, dst: Path, period: str) -> None:
        shutil.copyfile(src, dst)
        for mirror in self.cfg.archive.mirror_dirs:
            d = mirror / period
            d.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, d / dst.name)

    def _record_failures(self, mail: MailItem, res: Result, keep: list[Attachment]) -> None:
        """失败才留痕：写 _failed/failures.csv，并把没处理掉的 PDF 原样放进去，方便手动补。"""
        if self.dry_run:
            return
        fdir = self.cfg.failed_path
        fdir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        for i, att in enumerate(keep):
            (fdir / f"{stamp}-{i}-{att.filename}").write_bytes(att.data)
        log = fdir / "failures.csv"
        new = not log.exists()
        with log.open("a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["时间", "邮件主题", "原因"])
            for reason in res.failures:
                w.writerow([stamp, mail.subject[:120], reason])
