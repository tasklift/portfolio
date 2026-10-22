#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""books-sample-kit: 도서 목록 수집 / 내보내기 (표준 라이브러리만 사용)."""
import argparse
import datetime
import html
import json
import os
import re
import shutil
import struct
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import zipfile
import zlib
from xml.sax.saxutils import escape

ALLOWED = ["title", "price", "rating", "stock"]
COLNAME = {"title": "제목", "price": "가격", "rating": "평점", "stock": "재고"}
RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


class InputError(Exception):
    pass


class NetworkError(Exception):
    pass


def out(text=""):
    s = sys.stdout
    if s is not None:
        s.write(text + "\n")
        s.flush()


def err(text):
    s = sys.stderr
    if s is not None:
        s.write(text + "\n")
        s.flush()


class KoParser(argparse.ArgumentParser):
    def error(self, message):
        err("오류: 인자가 잘못되었거나 빠졌습니다 (%s). "
            "사용법: python main.py collect --url <주소> --config <설정파일> --out <결과폴더> "
            "또는 python main.py export --out <결과폴더> --site <내보낼폴더> 형식으로 다시 실행하세요." % message)
        sys.exit(2)


# ---------------------------------------------------------------- 입력 검사
def parse_args(argv):
    p = KoParser(prog="main.py", add_help=True)
    sub = p.add_subparsers(dest="cmd", parser_class=KoParser)
    c = sub.add_parser("collect")
    c.add_argument("--url", required=True)
    c.add_argument("--config", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--delay", type=float, default=1.0)
    c.add_argument("--retries", type=int, default=3)
    c.add_argument("--max-pages", dest="max_pages", type=int, default=None)
    e = sub.add_parser("export")
    e.add_argument("--out", required=True)
    e.add_argument("--site", required=True)
    a = p.parse_args(argv)
    if not a.cmd:
        err("오류: 서브커맨드가 없습니다. collect 또는 export 중 하나를 지정해 다시 실행하세요.")
        sys.exit(2)
    return a


def load_config(path):
    if not os.path.isfile(path):
        raise InputError("설정 파일을 찾을 수 없습니다: %s. --config 에 존재하는 JSON 파일 경로를 지정하세요." % path)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw = f.read()
    except (OSError, UnicodeDecodeError):
        raise InputError("설정 파일을 UTF-8 텍스트로 읽을 수 없습니다. UTF-8 JSON 파일로 저장해 다시 시도하세요.")
    if not raw.strip():
        raise InputError('설정 파일이 비어 있습니다. {"fields": ["title","price","rating","stock"]} 형식으로 작성하세요.')
    try:
        cfg = json.loads(raw)
    except ValueError:
        raise InputError("설정 파일이 올바른 JSON이 아닙니다. 따옴표와 쉼표를 확인해 고치세요.")
    if not isinstance(cfg, dict) or "fields" not in cfg:
        raise InputError('설정 파일은 {"fields": [...]} 형태의 JSON 객체여야 합니다.')
    fields = cfg["fields"]
    if not isinstance(fields, list) or not fields:
        raise InputError("fields 는 비어 있지 않은 목록이어야 합니다. 예: [\"title\",\"price\"].")
    seen = set()
    for x in fields:
        if not isinstance(x, str) or x not in ALLOWED:
            raise InputError("fields 에 허용되지 않는 값이 있습니다: %s. title, price, rating, stock 중에서만 고르세요." % (x,))
        if x in seen:
            raise InputError("fields 에 중복된 값이 있습니다: %s. 중복을 지우세요." % x)
        seen.add(x)
    return fields


def validate_collect(a):
    if not (a.url.startswith("http://") or a.url.startswith("https://")):
        raise InputError("--url 은 http:// 또는 https:// 로 시작해야 합니다. 예: https://books.toscrape.com")
    fields = load_config(a.config)
    if a.delay != a.delay or a.delay < 0 or a.delay == float("inf"):
        raise InputError("--delay 는 0 이상의 숫자여야 합니다. 예: --delay 1.0")
    if a.retries < 0:
        raise InputError("--retries 는 0 이상의 정수여야 합니다. 예: --retries 3")
    if a.max_pages is not None and a.max_pages < 1:
        raise InputError("--max-pages 는 1 이상의 정수여야 합니다. 예: --max-pages 5")
    return fields


# ---------------------------------------------------------------- 수집
class Fetcher:
    def __init__(self, delay, retries, log_path):
        self.delay = delay
        self.retries = retries
        self.log_path = log_path
        self.last = None
        self.requests = 0
        self.retries_used = 0

    def _wait(self):
        if self.last is not None:
            rest = self.delay - (time.monotonic() - self.last)
            if rest > 0:
                time.sleep(rest)

    def _log(self, f, url, attempt, ok, status, error):
        rec = {"time": datetime.datetime.now().isoformat(timespec="seconds"),
               "url": url, "attempt": attempt, "ok": ok, "status": status, "error": error}
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()

    def get(self, url):
        last_err = ""
        with open(self.log_path, "a", encoding="utf-8") as lf:
            for attempt in range(1, self.retries + 2):
                self._wait()
                self.requests += 1
                if attempt > 1:
                    self.retries_used += 1
                status = None
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "books-sample-kit/1.0"})
                    with urllib.request.urlopen(req, timeout=30) as r:
                        status = r.status
                        data = r.read()
                        final = r.geturl()
                    self.last = time.monotonic()
                    self._log(lf, url, attempt, True, status, None)
                    return data.decode("utf-8", errors="replace"), final
                except urllib.error.HTTPError as ex:
                    status = ex.code
                    last_err = "HTTP 오류 %s" % ex.code
                except urllib.error.URLError as ex:
                    last_err = "접속 실패: %s" % ex.reason
                except Exception as ex:  # 타임아웃, 연결 끊김 등
                    last_err = "요청 실패: %s" % ex
                self.last = time.monotonic()
                self._log(lf, url, attempt, False, status, last_err)
        raise NetworkError("%s 에 접속하지 못했습니다 (%d회 시도, %s). 주소와 인터넷 연결을 확인하고 다시 실행하세요."
                           % (url, self.retries + 1, last_err))


CARD_RE = re.compile(r'<article\b[^>]*class="[^"]*product_pod[^"]*"[^>]*>(.*?)</article>', re.S)
NEXT_RE = re.compile(r'<li\b[^>]*class="next"[^>]*>\s*<a\b[^>]*href="([^"]+)"', re.S)


def parse_page(text, base):
    books = []
    for m in CARD_RE.finditer(text):
        c = m.group(1)
        a = re.search(r'<h3>\s*<a\b[^>]*?href="([^"]+)"[^>]*?title="([^"]*)"', c, re.S)
        if not a:
            a2 = re.search(r'<h3>\s*<a\b[^>]*?title="([^"]*)"[^>]*?href="([^"]+)"', c, re.S)
            if not a2:
                continue
            href, title = a2.group(2), a2.group(1)
        else:
            href, title = a.group(1), a.group(2)
        pm = re.search(r'class="price_color"[^>]*>(.*?)</p>', c, re.S)
        price = None
        if pm:
            n = re.search(r'\d+(?:\.\d+)?', pm.group(1))
            if n:
                price = float(n.group(0))
        rm = re.search(r'class="star-rating\s+(\w+)"', c)
        rating = RATING_WORDS.get(rm.group(1)) if rm else None
        sm = re.search(r'class="[^"]*availability[^"]*"[^>]*>(.*?)</p>', c, re.S)
        stock = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", sm.group(1))).strip() if sm else ""
        books.append({"url": urllib.parse.urljoin(base, href), "title": html.unescape(title),
                      "price": price, "rating": rating, "stock": html.unescape(stock)})
    nm = NEXT_RE.search(text)
    nxt = urllib.parse.urljoin(base, nm.group(1)) if nm else None
    return books, nxt


# ---------------------------------------------------------------- xlsx
def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def cell(ref, v, style=0):
    st = ' s="%d"' % style if style else ""
    if isinstance(v, bool):
        v = int(v)
    if isinstance(v, (int, float)):
        return '<c r="%s"%s><v>%s</v></c>' % (ref, st, repr(v) if isinstance(v, float) else v)
    if v is None:
        return ""
    return '<c r="%s"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, st, escape(str(v)))


def sheet_xml(rows, ncols, freeze=False, afilter=False):
    x = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
         '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
    if freeze:
        x.append('<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
                 'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>')
    x.append("<sheetData>")
    for ri, row in enumerate(rows, 1):
        cs = "".join(cell("%s%d" % (col_letter(ci), ri), v, 1 if ri == 1 else 0) for ci, v in enumerate(row))
        x.append('<row r="%d">%s</row>' % (ri, cs))
    x.append("</sheetData>")
    if afilter:
        x.append('<autoFilter ref="A1:%s%d"/>' % (col_letter(max(ncols, 1) - 1), max(len(rows), 1)))
    x.append("</worksheet>")
    return "".join(x)


def write_xlsx(path, fields, books, changes):
    head = [COLNAME[f] for f in fields]
    rows1 = [head] + [[b[f] for f in fields] for b in books]
    prices = [b["price"] for b in books if b["price"] is not None]
    ratings = [b["rating"] for b in books if b["rating"] is not None]
    instock = sum(1 for b in books if str(b["stock"]).lower().startswith("in stock"))
    rows2 = [["항목", "값"],
             ["총 권수", len(books)],
             ["평균 가격", round(sum(prices) / len(prices), 2) if prices else 0],
             ["최저 가격", min(prices) if prices else 0],
             ["최고 가격", max(prices) if prices else 0],
             ["평균 평점", round(sum(ratings) / len(ratings), 2) if ratings else 0],
             ["재고 있음 권수", instock]]
    rows3 = [["제목", "이전 가격", "현재 가격", "차이"]] + \
            [[c["title"], c["old"], c["new"], round(c["new"] - c["old"], 2)] for c in changes]
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          + "".join('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % i for i in (1, 2, 3))
          + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
          '<sheet name="도서목록" sheetId="1" r:id="rId1"/>'
          '<sheet name="요약" sheetId="2" r:id="rId2"/>'
          '<sheet name="가격변경" sheetId="3" r:id="rId3"/>'
          '</sheets></workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              + "".join('<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' % (i, i) for i in (1, 2, 3))
              + '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
              '</Relationships>')
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
              '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
              '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
              '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
              '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
              '</styleSheet>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml(rows1, len(fields), freeze=True, afilter=True))
        z.writestr("xl/worksheets/sheet2.xml", sheet_xml(rows2, 2))
        z.writestr("xl/worksheets/sheet3.xml", sheet_xml(rows3, 4))


# ---------------------------------------------------------------- collect
def load_prev(path):
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        bl = d["books"]
        return [b for b in bl if isinstance(b, dict) and "url" in b]
    except Exception:
        return []


def cmd_collect(a):
    fields = validate_collect(a)
    os.makedirs(a.out, exist_ok=True)
    log_path = os.path.join(a.out, "run_log.jsonl")
    books_path = os.path.join(a.out, "books.json")
    prev = load_prev(books_path)
    fx = Fetcher(a.delay, a.retries, log_path)
    got = []
    url, pages = a.url, 0
    seen_pages = set()
    try:
        while url and url not in seen_pages:
            if a.max_pages is not None and pages >= a.max_pages:
                break
            seen_pages.add(url)
            text, final = fx.get(url)
            items, nxt = parse_page(text, final)
            got.extend(items)
            pages += 1
            url = nxt
    except NetworkError as ex:
        err("오류: %s" % ex)
        out(json.dumps({"command": "collect", "ok": False, "requests": fx.requests}, ensure_ascii=False))
        return 1

    # 같은 url 중복은 마지막 값 유지
    uniq = {}
    for b in got:
        uniq[b["url"]] = b
    got = list(uniq.values())

    prev_map = {b["url"]: b for b in prev}
    changes = []
    new_books = 0
    for b in got:
        p = prev_map.get(b["url"])
        if p is None:
            new_books += 1
        elif p.get("price") != b["price"]:
            changes.append({"url": b["url"], "title": b["title"], "old": p.get("price"), "new": b["price"]})
    merged = dict(prev_map)
    for b in got:
        merged[b["url"]] = b
    with open(books_path, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.datetime.now().isoformat(timespec="seconds"),
                   "books": list(merged.values())}, f, ensure_ascii=False, indent=1)
    xlsx_path = os.path.join(a.out, "books.xlsx")
    write_xlsx(xlsx_path, fields, got, changes)
    import csv
    with open(os.path.join(a.out, "books.csv"), "w", encoding="utf-8-sig", newline="") as cf:
        cw = csv.writer(cf)
        cw.writerow([COLNAME[k] for k in fields])
        for bk in got:
            cw.writerow([bk.get(k, "") for k in fields])

    out("수집 완료: %d쪽, %d권 (요청 %d회, 재시도 %d회)" % (pages, len(got), fx.requests, fx.retries_used))
    out("신규 %d권, 가격 변경 %d건" % (new_books, len(changes)))
    for c in changes:
        out("가격 변경: %s %s→%s" % (c["title"], c["old"], c["new"]))
    base = a.out.rstrip("/\\") if a.out.rstrip("/\\") else a.out
    out(json.dumps({"command": "collect", "pages": pages, "books": len(got), "requests": fx.requests,
                    "retries_used": fx.retries_used, "new_books": new_books,
                    "price_changes": len(changes), "changes": changes,
                    "xlsx": base + "/books.xlsx", "log": base + "/run_log.jsonl"}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- export
def make_png(counts, path):
    W, H = 640, 360
    px = [[(255, 255, 255)] * W for _ in range(H)]

    def rect(x0, y0, x1, y1, col):
        for y in range(max(y0, 0), min(y1, H)):
            row = px[y]
            for x in range(max(x0, 0), min(x1, W)):
                row[x] = col

    digits = {
        "1": ["010", "110", "010", "010", "111"],
        "2": ["111", "001", "111", "100", "111"],
        "3": ["111", "001", "111", "001", "111"],
        "4": ["101", "101", "111", "001", "001"],
        "5": ["111", "100", "111", "001", "111"],
        "0": ["111", "101", "101", "101", "111"],
        "6": ["111", "100", "111", "101", "111"],
        "7": ["111", "001", "010", "010", "010"],
        "8": ["111", "101", "111", "101", "111"],
        "9": ["111", "101", "111", "001", "111"],
    }

    def text(s, x, y, scale, col):
        for ch in s:
            for r, line in enumerate(digits[ch]):
                for c, bit in enumerate(line):
                    if bit == "1":
                        rect(x + c * scale, y + r * scale, x + (c + 1) * scale, y + (r + 1) * scale, col)
            x += 4 * scale

    left, right, top, bottom = 60, 610, 40, 310
    rect(left - 2, top, left, bottom, (60, 60, 60))
    rect(left - 2, bottom, right, bottom + 2, (60, 60, 60))
    mx = max(max(counts.values()), 1)
    cols = [(220, 80, 80), (230, 150, 60), (230, 200, 60), (110, 180, 90), (60, 130, 200)]
    slot = (right - left) // 5
    for i in range(5):
        n = counts[str(i + 1)]
        h = int((bottom - top - 30) * n / mx)
        x0 = left + i * slot + 20
        rect(x0, bottom - h, x0 + slot - 40, bottom, cols[i])
        s = str(n)
        text(s, x0 + (slot - 40) // 2 - len(s) * 6, bottom - h - 18, 3, (30, 30, 30))
        text(str(i + 1), x0 + (slot - 40) // 2 - 6, bottom + 12, 4, (30, 30, 30))
    raw = b"".join(b"\x00" + bytes(v for p in row for v in p) for row in px)

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def cmd_export(a):
    bp = os.path.join(a.out, "books.json")
    hint = "먼저 collect를 실행하세요 (python main.py collect --url <주소> --config <설정파일> --out %s)." % a.out
    if not os.path.isfile(bp) or os.path.getsize(bp) == 0:
        raise InputError("결과폴더에 books.json 이 없거나 비어 있습니다. " + hint)
    try:
        with open(bp, "r", encoding="utf-8") as f:
            d = json.load(f)
        books = d["books"]
        if not isinstance(books, list) or not all(isinstance(b, dict) for b in books):
            raise ValueError
    except Exception:
        raise InputError("books.json 형식이 올바르지 않습니다. " + hint)
    xp = os.path.join(a.out, "books.xlsx")
    if not os.path.isfile(xp):
        raise InputError("결과폴더에 books.xlsx 가 없습니다. " + hint)
    os.makedirs(a.site, exist_ok=True)
    counts = {str(i): 0 for i in range(1, 6)}
    for b in books:
        r = b.get("rating")
        if isinstance(r, int) and str(r) in counts:
            counts[str(r)] += 1
    prices = [b["price"] for b in books if isinstance(b.get("price"), (int, float))]
    avg = round(sum(prices) / len(prices), 2) if prices else 0
    make_png(counts, os.path.join(a.site, "sample.png"))
    shutil.copyfile(xp, os.path.join(a.site, "books_sample.xlsx"))
    lp = os.path.join(a.out, "run_log.jsonl")
    if os.path.isfile(lp):
        shutil.copyfile(lp, os.path.join(a.site, "run_log.jsonl"))
    else:
        open(os.path.join(a.site, "run_log.jsonl"), "w", encoding="utf-8").close()
    with open(os.path.join(a.site, "summary.json"), "w", encoding="utf-8") as f:
        json.dump({"books": len(books), "avg_price": avg, "rating_counts": counts}, f, ensure_ascii=False)
    out("내보내기 완료: %s 에 파일 4개를 만들었습니다 (%d권)." % (a.site, len(books)))
    out(json.dumps({"command": "export", "site": a.site,
                    "files": ["sample.png", "books_sample.xlsx", "run_log.jsonl", "summary.json"],
                    "books": len(books)}, ensure_ascii=False))
    return 0


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    a = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if a.cmd == "collect":
            return cmd_collect(a)
        return cmd_export(a)
    except InputError as ex:
        err("오류: %s" % ex)
        return 2


if __name__ == "__main__":
    sys.exit(main())
