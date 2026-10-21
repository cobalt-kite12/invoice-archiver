#!/usr/bin/env bash
# 独立的 bash 版本（与 python -m invoice_archiver nuonuo 等价）。
# 用法: nuonuo_fetch.sh <诺诺短链 https://nnfp.jss.com.cn/XXXX> <输出pdf路径>
set -euo pipefail
SHORT="$1"; OUT="$2"; UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
FINAL=$(curl -sSL -A "$UA" -o /dev/null -w '%{url_effective}' "$SHORT")
case "$FINAL" in https://nnfp.jss.com.cn/*) ;; *) echo "unexpected final url: $FINAL" >&2; exit 2;; esac
PL=$(python3 -c "import sys,urllib.parse as u;print(u.parse_qs(u.urlparse(sys.argv[1]).query)['paramList'][0])" "$FINAL")
J=$(curl -sS -A "$UA" -e "$FINAL" -X POST https://nnfp.jss.com.cn/scan2/getIvcDetailShow.do \
  --data-urlencode "paramList=$PL" --data "code=&aliView=true&invoiceDetailMiddleUri=&shortLinkSource=1")
PDF=$(python3 -c "import sys,json;d=json.loads(sys.argv[1]);assert d['status']=='0000',d.get('msg');print(d['data']['invoiceSimpleVo']['url'])" "$J")
case "$PDF" in https://inv.jss.com.cn/*|https://*.nuonuo.com/*|https://*.jss.com.cn/*) ;; *) echo "unexpected pdf host: $PDF" >&2; exit 3;; esac
curl -sSL --retry 5 --retry-all-errors --max-time 60 -A "$UA" -o "$OUT" "$PDF"
head -c 5 "$OUT" | grep -q '%PDF-' || { echo "not a pdf" >&2; exit 4; }
echo "ok $OUT"
