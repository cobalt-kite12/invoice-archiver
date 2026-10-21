"""诺诺网（nnfp.jss.com.cn）只给「下载发票」短链、没有附件时，取回 PDF。

流程：短链 → 302 跳到 printQrcode?paramList=… → POST paramList 到
scan2/getIvcDetailShow.do → 返回 JSON 里 data.invoiceSimpleVo.url 即 PDF。

注意：
* 每次下载都会让诺诺那边的下载计数 +1，所以一封邮件只取一次（由台账记录）。
* 接口返回里含购买方手机号/邮箱等个人信息，这里只取 PDF 地址，不打印、不落盘。
* 只访问白名单域名。
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120 Safari/537.36")
DETAIL_API = "https://nnfp.jss.com.cn/scan2/getIvcDetailShow.do"
LINK_RE = re.compile(r"https?://(?:nnfp\.jss\.com\.cn|of1\.cn)/[A-Za-z0-9_\-]{4,40}(?![A-Za-z0-9/_\-?])")
LANDING_HOSTS = ("nnfp.jss.com.cn",)
PDF_HOST_SUFFIXES = ("jss.com.cn", "nuonuo.com")


class NuonuoError(RuntimeError):
    pass


def find_links(text: str) -> list[str]:
    out: list[str] = []
    for m in LINK_RE.finditer(text):
        u = m.group(0).replace("http://", "https://", 1)
        if u not in out:
            out.append(u)
    return out


def _host_ok(url: str, suffixes: tuple[str, ...]) -> bool:
    p = urllib.parse.urlparse(url)
    h = (p.hostname or "").lower()
    return p.scheme == "https" and any(h == s or h.endswith("." + s) for s in suffixes)


def _open(req, timeout: int, retries: int):
    last: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except Exception as e:  # inv.jss.com.cn 偶发 TLS EOF，重试即可
            last = e
            time.sleep(min(2 ** attempt, 8))
    raise NuonuoError(f"请求失败：{type(last).__name__}")


def fetch_pdf(short_link: str, timeout: int = 30, retries: int = 5) -> bytes:
    # 1) 跟随短链跳转，拿到落地页
    req = urllib.request.Request(short_link, headers={"User-Agent": UA})
    with _open(req, timeout, retries) as r:
        landing = r.geturl()
    if not _host_ok(landing, LANDING_HOSTS):
        raise NuonuoError("短链跳到了意外的域名")
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(landing).query)
    if "paramList" not in qs:
        raise NuonuoError("落地页里没有 paramList")

    # 2) 查发票详情，只取 PDF 地址
    body = urllib.parse.urlencode({
        "paramList": qs["paramList"][0], "code": "", "aliView": "true",
        "invoiceDetailMiddleUri": "", "shortLinkSource": "1",
    }).encode()
    req = urllib.request.Request(DETAIL_API, data=body, headers={
        "User-Agent": UA, "Referer": landing,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    with _open(req, timeout, retries) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    if data.get("status") != "0000":
        raise NuonuoError(f"接口返回状态 {data.get('status')}")
    pdf_url = ((data.get("data") or {}).get("invoiceSimpleVo") or {}).get("url") or ""
    del data  # 含个人信息，尽早丢弃
    if not _host_ok(pdf_url, PDF_HOST_SUFFIXES):
        raise NuonuoError("PDF 地址不在白名单域名内")

    # 3) 下载 PDF
    req = urllib.request.Request(pdf_url, headers={"User-Agent": UA})
    with _open(req, timeout, retries) as r:
        pdf = r.read()
    if not pdf.startswith(b"%PDF-"):
        raise NuonuoError("下载到的不是 PDF")
    return pdf
