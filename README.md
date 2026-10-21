# invoice-archiver · 邮件发票自动归档

每个月报销，最烦的是在邮箱里一封封找发票、下载、改名、分文件夹。
这个小工具把这件事自动化：**邮件来一封，处理一封**——取出 PDF 发票，读出项目、金额、开票日期、发票号码，
按统一规则改名，放进按月份分好的文件夹，并记一本 CSV 台账防止重复。

- 只依赖 Python 3.11+ 标准库和 `pdftotext`（poppler-utils），没有第三方 Python 包
- 邮件来源：本地 `.eml` 文件 / 目录，或 IMAP 邮箱（只读，不改邮件状态）
- 只要 PDF，OFD / XML 一律忽略
- 支持只给「下载链接」不带附件的诺诺网发票
- 归档目录可以直接是网盘的本地同步文件夹，**代码里不需要任何网盘凭据**
- 成功时安静；失败才留痕（`_failed/failures.csv`，退出码非 0），方便接到定时任务或通知里

## 归档规则

| 发票类型 | 保留的文件 |
| --- | --- |
| 普通发票（停车、加油、通信等） | 发票 PDF |
| 网约车（如滴滴） | 发票 PDF + 行程单 PDF |
| 快递（如顺丰） | 发票 PDF + 运单明细 PDF |

**命名：** `项目-金额-MMDD.pdf`（不带年份，年份已经体现在月份文件夹里）

```
2026-10/
├── 停车费-1.50-1021.pdf
├── 停车费-1.50-1021-2.pdf          # 同名但发票号不同 → 加 -2、-3
├── 客运服务费-23.00-1003.pdf
├── 客运服务费-23.00-1003-行程单.pdf
├── 收派服务费-8.00-1009.pdf
└── 收派服务费-8.00-1009-运单明细.pdf
```

- 项目：取发票上第一条「项目名称」，去掉 `*分类*` 前缀（`*生产生活服务*停车费` → `停车费`）
- 金额：价税合计（小写），两位小数
- 日期：开票日期的月日
- 月份文件夹 `YYYY-MM`：默认按自然月；如果你的报销周期是「21 日到次月 20 日」，设 `cycle_start_day = 21`，21 日及以后开的票会归到下个月
- 去重：同一发票号只归档一次（不管被转发几次）；同一封邮件也只处理一次

## 安装

```bash
# macOS
brew install poppler
# Debian / Ubuntu
sudo apt install poppler-utils

git clone <本仓库地址> && cd invoice-archiver
pip install .            # 或者不安装，直接 python -m invoice_archiver
```

## 使用

```bash
cp config.example.toml config.toml   # 改 output_dir 等

# 1) 处理导出的 .eml（文件或目录都行）
python -m invoice_archiver eml ~/Downloads/发票邮件/ -c config.toml -v

# 2) 按配置读 IMAP 邮箱
export INVOICE_IMAP_PASSWORD='邮箱授权码'
python -m invoice_archiver run -c config.toml

# 调试：看一张 PDF 能解析出什么
python -m invoice_archiver parse 某张发票.pdf

# 单独下载一张诺诺网发票
python -m invoice_archiver nuonuo https://nnfp.jss.com.cn/XXXXXXXX out.pdf
```

`--dry-run` 只解析不写文件。

### 定时运行

例如每 10 分钟查一次邮箱（crontab）：

```
*/10 * * * * cd /path/to/invoice-archiver && INVOICE_IMAP_PASSWORD=... python3 -m invoice_archiver run -c config.toml
```

已处理过的邮件会自动跳过，所以 `since_days` 可以设大一点也没关系。

### 存到网盘

把 `output_dir` 设成网盘客户端的本地同步目录即可，例如：

- Google Drive：`~/Library/CloudStorage/GoogleDrive-…/我的云端硬盘/发票`
- OneDrive / iCloud / 坚果云 / 群晖 Drive 同理

想同时再放一份到别处，用 `mirror_dirs`。

### 邮箱设置提示

- **QQ 邮箱 / 163 等**：IMAP 需要在网页版设置里开启，密码处填「授权码」而不是登录密码
- **不想给 IMAP 权限？** 在邮箱里设置「自动转发」到一个专门收发票的邮箱，或者定期把发票邮件导出为 `.eml` 丢进 `eml_dir`
- 授权码只从环境变量读取；配置文件里写 `password` 会直接报错

## 诺诺网链接发票是怎么取的

有些开票平台（诺诺网）邮件里只有一个「下载发票」短链，没有附件。工具会：

1. 跟随短链跳转，落到 `nnfp.jss.com.cn/scan-invoice/printQrcode?paramList=…`
2. 把 `paramList` POST 到 `nnfp.jss.com.cn/scan2/getIvcDetailShow.do`（Referer 设为落地页）
3. 从返回 JSON 的 `data.invoiceSimpleVo.url` 拿到 PDF 地址并下载（偶发 TLS 断开，自动重试）

注意：

- 只访问 `jss.com.cn` / `nuonuo.com` 的 https 地址，其它域名直接拒绝
- 诺诺那边每下载一次计数 +1，所以同一封邮件只取一次
- 接口返回里有购买方手机号等个人信息，工具只取 PDF 地址，不打印、不保存
- 这是网页前端用的接口，不是官方开放 API，平台改版可能失效；失效时会记为失败，不会乱存文件

## 台账

`output_dir/ledger.csv`（UTF-8 带 BOM，Excel 可直接打开）：

`开票日期, 项目, 金额, 销售方, 发票号, 文件名, 附带文件, 归档目录, 来源邮件主题, 归档时间`

> 用 Excel 打开时，20 位发票号码可能被显示成科学计数法，这是显示问题，文件里是完整的。

`ledger.messages.txt` 记录已处理邮件的 Message-ID 哈希。

## 解析不准怎么办

不同平台的 PDF 版式差别很大，解析是尽力而为：

- 读不出关键字段 → 不归档，PDF 原样放进 `_failed/` 并写一行原因，手动处理即可
- 项目名称被折行读错（例如 `收派服务` 少了 `费`）→ 在配置里加 `[item_aliases]` 修正
- 欢迎提 issue 附上**打码后**的 `pdftotext -layout` 输出，帮忙适配更多版式

## 开发

```bash
python3 -m unittest discover -s tests -t .
```

测试用的 PDF 全部在测试里现场合成（`tests/pdfgen.py`，纯标准库），发票号、金额、公司名都是虚构的，仓库里不包含任何真实发票。

## 隐私

- 发票、行程单、运单明细里有手机号、姓名、地址等个人信息，**不要把它们提交进 git**（`.gitignore` 已默认忽略 pdf / eml / 台账）
- 提 issue 前请先打码

---

## English

**invoice-archiver** files Chinese e-invoices (电子发票) that arrive by email.

- Reads `.eml` files or an IMAP mailbox (read-only)
- Keeps PDFs only (ignores OFD/XML); fetches PDFs for link-only invoices from Nuonuo (诺诺网)
- Parses each invoice with `pdftotext` for item, total, issue date and invoice number
- Saves it as `ITEM-AMOUNT-MMDD.pdf` in `YYYY-MM/` folders. Ride-hailing trip sheets (行程单) and courier waybill details (运单明细) are kept next to their invoice, with a suffix added to the name.
- Deduplicates by invoice number using a CSV ledger
- Point `output_dir` at any locally synced cloud folder; no cloud credentials are needed
- Silent on success. Failures go to `_failed/failures.csv` and the command exits non-zero.

Requirements: Python 3.11+ and poppler-utils. No third-party Python packages.
Quick start: `cp config.example.toml config.toml && python -m invoice_archiver eml path/to/mails -c config.toml -v`.
Tests: `python3 -m unittest discover -s tests -t .` (synthetic data only).

License: MIT.
