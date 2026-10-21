import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from invoice_archiver.naming import base_stem, companion_name, period_of, unique_stem
from invoice_archiver.parse import INVOICE, TRIP, WAYBILL, classify, parse_pdf, parse_text
from tests.pdfgen import companion_pdf, invoice_pdf


class ParseTest(unittest.TestCase):
    def _pdf(self, data: bytes) -> Path:
        d = tempfile.mkdtemp()
        p = Path(d) / "x.pdf"
        p.write_bytes(data)
        return p

    def test_basic_invoice(self):
        doc = parse_pdf(self._pdf(invoice_pdf("00000000000000000011", 2026, 3, 7,
                                              "生产生活服务", "停车费", "1.50")))
        self.assertEqual(doc.kind, INVOICE)
        self.assertEqual(doc.invoice_no, "00000000000000000011")
        self.assertEqual(doc.issue_date, date(2026, 3, 7))
        self.assertEqual(doc.item, "停车费")
        self.assertEqual(doc.amount, Decimal("1.50"))
        self.assertEqual(doc.seller, "示例服务有限公司")
        self.assertEqual(doc.missing(), [])

    def test_wrapped_item_name(self):
        doc = parse_pdf(self._pdf(invoice_pdf("00000000000000000012", 2026, 3, 7,
                                              "交通运输服务", "客运服务", "23.00", wrap="费")))
        self.assertEqual(doc.item, "客运服务费")

    def test_alias(self):
        doc = parse_text("发票号码：12345678\n开票日期：2026-01-02\n*a*收派服务  （小写）¥9.00",
                         aliases={"收派服务": "收派服务费"})
        self.assertEqual(doc.item, "收派服务费")
        self.assertEqual(doc.issue_date, date(2026, 1, 2))

    def test_classify_companions(self):
        self.assertEqual(classify("", "示例出行行程报销单.pdf"), TRIP)
        self.assertEqual(parse_pdf(self._pdf(companion_pdf("行程单", "23.00"))).kind, TRIP)
        self.assertEqual(parse_pdf(self._pdf(companion_pdf("发票运单明细", "8.00"))).kind, WAYBILL)

    def test_unknown_is_flagged(self):
        doc = parse_text("随便一段文字")
        self.assertEqual(doc.kind, "未知")


class NamingTest(unittest.TestCase):
    def test_stem(self):
        self.assertEqual(base_stem("停车费", Decimal("1.5"), date(2026, 10, 21)), "停车费-1.50-1021")
        self.assertEqual(base_stem("a/b c", Decimal("2"), date(2026, 1, 2)), "abc-2.00-0102")

    def test_unique(self):
        taken = {"停车费-1.50-1021", "停车费-1.50-1021-2"}
        self.assertEqual(unique_stem("停车费-1.50-1021", taken.__contains__), "停车费-1.50-1021-3")
        self.assertEqual(unique_stem("油费-1.00-0101", taken.__contains__), "油费-1.00-0101")

    def test_companion(self):
        self.assertEqual(companion_name("客运服务费-23.00-0307", "行程单"), "客运服务费-23.00-0307-行程单.pdf")

    def test_period(self):
        self.assertEqual(period_of(date(2026, 10, 20)), "2026-10")
        self.assertEqual(period_of(date(2026, 10, 20), 21), "2026-10")
        self.assertEqual(period_of(date(2026, 10, 21), 21), "2026-11")
        self.assertEqual(period_of(date(2026, 12, 25), 21), "2027-01")


if __name__ == "__main__":
    unittest.main()
