import csv
import tempfile
import unittest
from pathlib import Path

from invoice_archiver import nuonuo
from invoice_archiver.archiver import Archiver
from invoice_archiver.config import load_config
from tests.helpers import make_config, make_eml
from tests.pdfgen import companion_pdf, invoice_pdf

ROOT = Path(__file__).resolve().parents[1]


def files(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.glob("*.pdf")) if folder.exists() else []


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = make_config(self.tmp)
        self.out = self.cfg.archive.output_dir

    def arch(self, **kw):
        return Archiver(self.cfg, **kw)

    def test_ordinary_pdf_only(self):
        pdf = invoice_pdf("00000000000000000101", 2026, 10, 21, "生产生活服务", "停车费", "1.50")
        raw = make_eml("停车发票", [("发票.pdf", pdf), ("发票.ofd", b"OFD"), ("发票.xml", b"<x/>")])
        res = self.arch().process_raw(raw)
        self.assertEqual(res.failures, [])
        self.assertEqual(files(self.out / "2026-10"), ["停车费-1.50-1021.pdf"])
        with (self.out / "ledger.csv").open(encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(rows[0]["发票号"], "00000000000000000101")
        self.assertEqual(rows[0]["金额"], "1.50")

    def test_trip_companion(self):
        inv = invoice_pdf("00000000000000000102", 2026, 10, 3, "交通运输服务", "客运服务", "23.00", wrap="费")
        raw = make_eml("出行发票", [("电子发票.pdf", inv), ("行程报销单.pdf", companion_pdf("行程单", "23.00"))])
        res = self.arch().process_raw(raw)
        self.assertEqual(res.failures, [])
        self.assertEqual(files(self.out / "2026-10"),
                         ["客运服务费-23.00-1003-行程单.pdf", "客运服务费-23.00-1003.pdf"])

    def test_waybill_companion(self):
        inv = invoice_pdf("00000000000000000103", 2026, 10, 9, "生产生活服务", "收派服务费", "8.00")
        raw = make_eml("快递发票", [("电子发票.pdf", inv), ("发票.ofd", b"OFD"),
                                   ("运单明细.pdf", companion_pdf("发票运单明细", "8.00"))])
        self.arch().process_raw(raw)
        self.assertEqual(files(self.out / "2026-10"),
                         ["收派服务费-8.00-1009-运单明细.pdf", "收派服务费-8.00-1009.pdf"])

    def test_dedupe_and_collision(self):
        a = invoice_pdf("00000000000000000201", 2026, 10, 5, "生产生活服务", "停车费", "5.00")
        b = invoice_pdf("00000000000000000202", 2026, 10, 5, "生产生活服务", "停车费", "5.00")
        arch = self.arch()
        arch.process_raw(make_eml("第一封", [("a.pdf", a)], msgid="<1@example.com>"))
        # 同一张发票换一封邮件再来一次：按发票号跳过
        res = arch.process_raw(make_eml("转发", [("a.pdf", a)], msgid="<2@example.com>"))
        self.assertEqual(res.duplicates, ["00000000000000000201"])
        # 同名不同号：加 -2
        arch.process_raw(make_eml("第二张", [("b.pdf", b)], msgid="<3@example.com>"))
        self.assertEqual(files(self.out / "2026-10"), ["停车费-5.00-1005-2.pdf", "停车费-5.00-1005.pdf"])
        # 同一封邮件重复处理：直接跳过
        self.assertTrue(arch.process_raw(make_eml("第二张", [("b.pdf", b)], msgid="<3@example.com>")).skipped_message)
        # 重新打开台账也能去重
        res = self.arch().process_raw(make_eml("再转发", [("a.pdf", a)], msgid="<4@example.com>"))
        self.assertEqual(res.duplicates, ["00000000000000000201"])

    def test_cycle_start_day(self):
        self.cfg.archive.cycle_start_day = 21
        pdf = invoice_pdf("00000000000000000301", 2026, 10, 25, "生产生活服务", "停车费", "3.00")
        self.arch().process_raw(make_eml("x", [("a.pdf", pdf)]))
        self.assertEqual(files(self.out / "2026-11"), ["停车费-3.00-1025.pdf"])

    def test_nuonuo_link_only(self):
        pdf = invoice_pdf("00000000000000000401", 2026, 10, 12, "生产生活服务", "停车费", "2.00")
        calls = []

        def fake_fetch(url):
            calls.append(url)
            return pdf

        html = '<a href="https://nnfp.jss.com.cn/AbCd1234">下载发票</a>'
        raw = make_eml("您收到一张电子发票", body="请点击链接下载", html=html)
        res = Archiver(self.cfg, fetcher=fake_fetch).process_raw(raw)
        self.assertEqual(res.failures, [])
        self.assertEqual(calls, ["https://nnfp.jss.com.cn/AbCd1234"])
        self.assertEqual(files(self.out / "2026-10"), ["停车费-2.00-1012.pdf"])
        # 再处理同一封邮件不会再次下载（诺诺有下载计数）
        Archiver(self.cfg, fetcher=fake_fetch).process_raw(raw)
        self.assertEqual(len(calls), 1)

    def test_failure_is_recorded(self):
        raw = make_eml("您的电子发票", body="你好")
        res = self.arch().process_raw(raw)
        self.assertTrue(res.failures)
        self.assertTrue((self.cfg.failed_path / "failures.csv").exists())
        # 同一封不会每次重复报错
        self.assertTrue(self.arch().process_raw(raw).skipped_message)

    def test_non_invoice_mail_is_silent(self):
        res = self.arch().process_raw(make_eml("周末聚餐", body="你好"))
        self.assertEqual(res.failures, [])
        self.assertTrue(res.skipped_message)

    def test_nuonuo_failure_retries_next_time(self):
        def boom(url):
            raise nuonuo.NuonuoError("网络错误")
        raw = make_eml("电子发票", html='<a href="https://nnfp.jss.com.cn/Qq11Ww22">下载</a>')
        self.assertTrue(Archiver(self.cfg, fetcher=boom).process_raw(raw).failures)
        pdf = invoice_pdf("00000000000000000701", 2026, 10, 2, "生产生活服务", "停车费", "4.00")
        res = Archiver(self.cfg, fetcher=lambda u: pdf).process_raw(raw)
        self.assertEqual(len(res.filed), 1)

    def test_unparseable_pdf_kept_for_manual(self):
        from tests.pdfgen import make_pdf
        bad = make_pdf([(40, 500, "这不是发票")])
        res = self.arch().process_raw(make_eml("奇怪的附件", [("x.pdf", bad)]))
        self.assertTrue(res.failures)
        self.assertEqual(len(list(self.cfg.failed_path.glob("*.pdf"))), 1)

    def test_mirror_dir(self):
        mirror = self.tmp / "synced"
        self.cfg.archive.mirror_dirs = [mirror]
        pdf = invoice_pdf("00000000000000000501", 2026, 10, 1, "生产生活服务", "汽油", "100.00")
        self.arch().process_raw(make_eml("油票", [("a.pdf", pdf)]))
        self.assertEqual(files(mirror / "2026-10"), ["汽油-100.00-1001.pdf"])

    def test_dry_run_writes_nothing(self):
        pdf = invoice_pdf("00000000000000000601", 2026, 10, 1, "生产生活服务", "停车费", "1.00")
        res = self.arch(dry_run=True).process_raw(make_eml("x", [("a.pdf", pdf)]))
        self.assertEqual(len(res.filed), 1)
        self.assertFalse(self.out.exists())

    def test_example_config_loads(self):
        cfg = load_config(ROOT / "config.example.toml")
        self.assertEqual(cfg.source_type, "eml")


class NuonuoLinkTest(unittest.TestCase):
    def test_find_links(self):
        text = "下载 https://nnfp.jss.com.cn/Ab12Cd34 或 http://of1.cn/Zz99Yy88 ，重复 https://nnfp.jss.com.cn/Ab12Cd34"
        self.assertEqual(nuonuo.find_links(text),
                         ["https://nnfp.jss.com.cn/Ab12Cd34", "https://of1.cn/Zz99Yy88"])
        self.assertEqual(nuonuo.find_links("https://nnfp.jss.com.cn/scan-invoice/printQrcode?x=1"), [])

    def test_host_allowlist(self):
        self.assertTrue(nuonuo._host_ok("https://inv.jss.com.cn/fp2/a.pdf", nuonuo.PDF_HOST_SUFFIXES))
        self.assertFalse(nuonuo._host_ok("https://evil.example.com/jss.com.cn.pdf", nuonuo.PDF_HOST_SUFFIXES))
        self.assertFalse(nuonuo._host_ok("http://inv.jss.com.cn/a.pdf", nuonuo.PDF_HOST_SUFFIXES))


if __name__ == "__main__":
    unittest.main()
