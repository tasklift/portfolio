"""사이트 변경 비교기: collect / diff / report (표준 라이브러리만 사용)."""
import argparse
import html
import io
import json
import os
import re
import sys
import time
import zipfile
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime

DEFAULT_UA = "portfolio-change-watcher/1.0"
LABEL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
HEADERS = ["구분", "사이트", "키", "항목", "이전값", "이후값"]


class UserError(Exception):
    pass


class KoreanHelpFormatter(argparse.HelpFormatter):
    def _format_usage(self, usage, actions, groups, prefix):
        return super()._format_usage(usage, actions, groups, "사용법: " if prefix is None else prefix)


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs):
        kwargs["formatter_class"] = KoreanHelpFormatter
        add_help = kwargs.pop("add_help", True)
        super().__init__(*args, add_help=False, **kwargs)
        self._positionals.title = "명령"
        self._optionals.title = "옵션"
        if add_help:
            self.add_argument("-h", "--help", action="help", help="도움말을 보고 종료합니다")

    def error(self, message):
        # 분석기의 내부 오류 문장은 분류에만 쓰고 원문은 출력하지 않는다.
        options = ", ".join(dict.fromkeys(re.findall(r"--[A-Za-z][A-Za-z0-9_-]*", message)))
        if message.startswith("the following arguments are required:"):
            guidance = "필수 옵션이 빠졌습니다: %s. 해당 옵션과 값을 함께 입력해 주세요." % options
        elif message.startswith("argument 명령: invalid choice:"):
            guidance = "알 수 없는 명령입니다. collect, diff, report 중 하나를 입력해 주세요."
        elif message.startswith("unrecognized arguments:"):
            guidance = "알 수 없는 옵션 또는 인자가 있습니다. --help에서 옵션 이름을 확인하고 불필요한 인자를 지워 주세요."
        elif "expected one argument" in message:
            guidance = "옵션 %s에 값이 없습니다. 옵션 바로 뒤에 값을 입력해 주세요." % options
        elif message.startswith("ambiguous option:"):
            guidance = "옵션 이름을 구분할 수 없습니다. --help에 나온 옵션 이름을 끝까지 입력해 주세요."
        else:
            guidance = "인자를 해석할 수 없습니다. --help에서 명령과 필수 옵션, 값의 입력 방법을 확인해 주세요."
        raise UserError(guidance)


def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def check_label(label):
    if not LABEL_RE.match(label or ""):
        raise UserError("라벨 '%s' 은 사용할 수 없습니다. 영문·숫자·-·_ 만 쓰도록 고쳐 주세요." % label)


# ---------------------------------------------------------------- 설정
def load_config(path):
    if not os.path.isfile(path):
        raise UserError("설정 파일을 찾을 수 없습니다. --config 경로를 확인해 주세요.")
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        raise UserError("설정 파일을 읽을 수 없습니다. UTF-8 텍스트 파일인지 확인해 주세요.")
    if not text.strip():
        raise UserError("설정 파일이 비어 있습니다. sites 가 들어 있는 JSON 내용을 채워 주세요.")
    try:
        cfg = json.loads(text)
    except ValueError:
        raise UserError("설정 파일이 올바른 JSON 이 아닙니다. 쉼표·따옴표 등 문법을 확인해 주세요.")
    if not isinstance(cfg, dict):
        raise UserError("설정 파일의 최상위는 객체여야 합니다. { \"sites\": [...] } 형태로 고쳐 주세요.")
    sites = cfg.get("sites")
    if not isinstance(sites, list) or not sites:
        raise UserError("설정에 sites 가 없거나 비어 있습니다. 사이트를 1개 이상 추가해 주세요.")
    ua = cfg.get("user_agent", DEFAULT_UA)
    if not isinstance(ua, str) or not ua.strip():
        ua = DEFAULT_UA
    interval = cfg.get("min_interval_sec", 1.0)
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval < 0:
        raise UserError("min_interval_sec 는 0 이상의 숫자여야 합니다. 값을 고쳐 주세요.")
    out_sites = []
    for i, s in enumerate(sites):
        if not isinstance(s, dict):
            raise UserError("sites[%d] 가 객체가 아닙니다. name·urls·item_regex·key_field 를 넣어 주세요." % i)
        for k in ("name", "urls", "item_regex", "key_field"):
            if k not in s or s[k] in (None, "", []):
                raise UserError("sites[%d] 에 '%s' 항목이 없습니다. 설정에 추가해 주세요." % (i, k))
        if not isinstance(s["name"], str) or not isinstance(s["item_regex"], str) \
                or not isinstance(s["key_field"], str):
            raise UserError("sites[%d] 의 name·item_regex·key_field 는 문자열이어야 합니다." % i)
        urls = s["urls"]
        if not isinstance(urls, list) or not all(isinstance(u, str) for u in urls):
            raise UserError("sites[%d].urls 는 URL 문자열 목록이어야 합니다. 형식을 고쳐 주세요." % i)
        for u in urls:
            p = urllib.parse.urlparse(u)
            if p.scheme not in ("http", "https") or not p.netloc:
                raise UserError("URL '%s' 은 http/https 주소가 아닙니다. 올바른 주소로 고쳐 주세요." % u)
        try:
            rx = re.compile(s["item_regex"], re.DOTALL)
        except re.error:
            raise UserError("sites[%d].item_regex 가 올바른 정규식이 아닙니다. 식을 확인해 주세요." % i)
        if s["key_field"] not in rx.groupindex:
            raise UserError("key_field '%s' 이(가) item_regex 의 이름 있는 그룹에 없습니다. "
                            "그룹 이름을 맞춰 주세요." % s["key_field"])
        out_sites.append({"name": s["name"], "urls": urls, "rx": rx, "key_field": s["key_field"]})
    return ua, float(interval), out_sites


# ---------------------------------------------------------------- collect
def fetch(url, ua, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": ua})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        charset = r.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def load_robots(url, ua, cache):
    p = urllib.parse.urlparse(url)
    base = "%s://%s" % (p.scheme, p.netloc)
    if base in cache:
        return cache[base]
    rp = urllib.robotparser.RobotFileParser()
    try:
        req = urllib.request.Request(base + "/robots.txt", headers={"User-Agent": ua})
        with urllib.request.urlopen(req, timeout=10) as r:
            rp.parse(r.read().decode("utf-8", errors="replace").splitlines())
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            rp.disallow_all = True
        else:
            rp.allow_all = True
    except Exception:
        rp.allow_all = True
    cache[base] = rp
    return rp


def cmd_collect(args):
    check_label(args.label)
    ua, interval, sites = load_config(args.config)
    start = time.monotonic()
    os.makedirs(os.path.join(args.out, "snapshots"), exist_ok=True)
    cache = {}
    last_req = None
    records = []
    tot_ok = tot_fail = tot_skip = 0
    log_lines = []
    for s in sites:
        ok = fail = skip = 0
        seen = set()
        rows = 0
        for url in s["urls"]:
            rp = load_robots(url, ua, cache)
            if not rp.can_fetch(ua, url):
                skip += 1
                print("건너뜀(robots.txt 금지): %s" % url)
                continue
            if last_req is not None:
                wait = interval - (time.perf_counter() - last_req)
                while wait > 0:
                    time.sleep(wait)
                    wait = interval - (time.perf_counter() - last_req)
            last_req = time.perf_counter()
            try:
                body = fetch(url, ua)
            except Exception as e:
                last_req = time.perf_counter()
                fail += 1
                print("실패: %s (%s)" % (url, e))
                continue
            last_req = time.perf_counter()
            ok += 1
            for m in s["rx"].finditer(body):
                fields = {k: (v if v is not None else "").strip() for k, v in m.groupdict().items()}
                key = fields[s["key_field"]]
                if key in seen:
                    continue
                seen.add(key)
                rows += 1
                records.append({"site": s["name"], "key": key, "fields": fields})
        tot_ok += ok
        tot_fail += fail
        tot_skip += skip
        log_lines.append("%s | collect | %s | %s | 성공 %d | 실패 %d | 건너뜀 %d | 행 %d"
                         % (now_iso(), args.label, s["name"], ok, fail, skip, rows))
        print("%s: 성공 %d, 실패 %d, 건너뜀 %d, 행 %d" % (s["name"], ok, fail, skip, rows))
    snap_path = os.path.join(args.out, "snapshots", args.label + ".json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump({"label": args.label, "collected_at": now_iso(), "records": records},
                  f, ensure_ascii=False, indent=1)
    with open(os.path.join(args.out, "run.log"), "a", encoding="utf-8", newline="\n") as f:
        for ln in log_lines:
            f.write(ln + "\n")
    elapsed = round(time.monotonic() - start, 3)
    print("수집 완료: 라벨 %s, 전체 행 %d, 소요 %.3f초" % (args.label, len(records), elapsed))
    result = {"command": "collect", "label": args.label, "ok": tot_ok, "fail": tot_fail,
              "skipped": tot_skip, "rows": len(records), "elapsed_sec": elapsed,
              "snapshot": snap_path}
    print(json.dumps(result, ensure_ascii=False))
    return 1 if (tot_ok == 0 and tot_fail > 0) else 0


# ---------------------------------------------------------------- diff
def load_snapshot(out, label):
    check_label(label)
    path = os.path.join(out, "snapshots", label + ".json")
    if not os.path.isfile(path):
        raise UserError("라벨 '%s' 의 스냅샷을 찾을 수 없습니다. 먼저 collect 로 수집하거나 "
                        "라벨 이름을 확인해 주세요." % label)
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        recs = data["records"]
        return {(r["site"], r["key"]): r["fields"] for r in recs}
    except (ValueError, KeyError, TypeError):
        raise UserError("스냅샷 '%s' 파일이 손상되었습니다. collect 를 다시 실행해 주세요." % label)


def fmt_fields(fields):
    return "; ".join("%s=%s" % (k, v) for k, v in fields.items())


def compute_diff(out, before, after):
    b = load_snapshot(out, before)
    a = load_snapshot(out, after)
    rows = []
    added = removed = changed = unchanged = 0
    for (site, key), bf in b.items():
        if (site, key) not in a:
            removed += 1
            rows.append(["삭제", site, key, "", fmt_fields(bf), ""])
        else:
            af = a[(site, key)]
            if af == bf:
                unchanged += 1
            else:
                changed += 1
                names = list(af.keys()) + [k for k in bf.keys() if k not in af]
                for n in names:
                    if bf.get(n) != af.get(n):
                        rows.append(["변경", site, key, n, str(bf.get(n, "")), str(af.get(n, ""))])
    for (site, key), af in a.items():
        if (site, key) not in b:
            added += 1
            rows.append(["추가", site, key, "", "", fmt_fields(af)])
    return rows, added, removed, changed, unchanged


_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def xml_esc(s):
    s = _ILLEGAL.sub("", str(s))
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def col_name(i):
    return "ABCDEFGHIJ"[i]


def write_xlsx(path, rows):
    all_rows = [HEADERS] + rows
    sheet = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>']
    for r, row in enumerate(all_rows, 1):
        sheet.append('<row r="%d">' % r)
        for c in range(6):
            v = row[c] if c < len(row) else ""
            sheet.append('<c r="%s%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                         % (col_name(c), r, xml_esc(v)))
        sheet.append("</row>")
    sheet.append("</sheetData></worksheet>")
    files = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '</Types>',
        "_rels/.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        "xl/workbook.xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="변경" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>',
        "xl/worksheets/sheet1.xml": "".join(sheet),
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content.encode("utf-8"))


def cmd_diff(args):
    rows, added, removed, changed, unchanged = compute_diff(args.out, args.before, args.after)
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "diff.xlsx")
    write_xlsx(path, rows)
    print("비교 %s → %s: 추가 %d, 삭제 %d, 변경 %d, 변경 없음 %d" %
          (args.before, args.after, added, removed, changed, unchanged))
    print(json.dumps({"command": "diff", "added": added, "removed": removed,
                      "changed": changed, "unchanged": unchanged, "xlsx": path},
                     ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- report
def cmd_report(args):
    rows, added, removed, changed, unchanged = compute_diff(args.out, args.before, args.after)
    log_path = os.path.join(args.out, "run.log")
    tail = []
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            tail = f.read().splitlines()[-20:]
    e = html.escape
    parts = ['<!DOCTYPE html>', '<html lang="ko"><head><meta charset="utf-8">',
             '<title>사이트 변경 비교 결과</title>',
             '<style>body{font-family:sans-serif;margin:2em}table{border-collapse:collapse}'
             'td,th{border:1px solid #bbb;padding:4px 8px}th{background:#eee}'
             'pre{background:#f6f6f6;padding:1em}</style></head><body>',
             '<h1>사이트 변경 비교 결과</h1>',
             '<p>%s → %s</p>' % (e(args.before), e(args.after)),
             '<p>추가 %d · 삭제 %d · 변경 %d</p>' % (added, removed, changed),
             '<table><thead><tr>%s</tr></thead><tbody>' % "".join("<th>%s</th>" % h for h in HEADERS)]
    for r in rows:
        parts.append("<tr>%s</tr>" % "".join("<td>%s</td>" % e(str(v)) for v in r))
    parts.append("</tbody></table>")
    parts.append("<h2>실행 로그 (최근 20줄)</h2><pre>%s</pre>" % e("\n".join(tail)))
    parts.append("</body></html>")
    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))
    print("보기 페이지를 만들었습니다: 추가 %d, 삭제 %d, 변경 %d" % (added, removed, changed))
    print(json.dumps({"command": "report", "html": path, "added": added,
                      "removed": removed, "changed": changed}, ensure_ascii=False))
    return 0


def build_parser():
    p = Parser(prog="main.py", description="사이트를 수집하고 두 수집 기록의 변경 내용을 비교합니다.")
    sub = p.add_subparsers(dest="cmd", parser_class=Parser, metavar="명령")
    c = sub.add_parser("collect", help="설정에 따라 사이트를 수집합니다",
                       description="허용된 주소를 요청 간격에 맞춰 수집하고 기록을 저장합니다.")
    c.add_argument("--config", required=True, metavar="설정파일", help="수집할 사이트가 담긴 JSON 파일 경로")
    c.add_argument("--out", required=True, metavar="결과폴더", help="수집 기록과 실행 로그를 저장할 폴더")
    c.add_argument("--label", required=True, metavar="라벨", help="수집 기록 이름: 영문·숫자·-·_만 사용")
    for name in ("diff", "report"):
        description = "두 수집 기록의 변경분을 엑셀 파일로 만듭니다" if name == "diff" else "두 수집 기록의 변경분을 보기 페이지로 만듭니다"
        d = sub.add_parser(name, help=description, description=description + ".")
        d.add_argument("--out", required=True, metavar="결과폴더", help="수집 기록이 있고 결과를 저장할 폴더")
        d.add_argument("--before", required=True, metavar="이전라벨", help="이전 수집 기록의 라벨")
        d.add_argument("--after", required=True, metavar="이후라벨", help="이후 수집 기록의 라벨")
    return p


def main(argv=None):
    for st in (sys.stdout, sys.stderr):
        try:
            st.reconfigure(encoding="utf-8")
        except Exception:
            pass
    try:
        args = build_parser().parse_args(argv)
        if not args.cmd:
            raise UserError("서브커맨드가 없습니다. collect, diff, report 중 하나를 지정해 주세요.")
        return {"collect": cmd_collect, "diff": cmd_diff, "report": cmd_report}[args.cmd](args)
    except UserError as e:
        sys.stderr.write(str(e) + "\n")
        return 2
    except SystemExit as e:  # --help 등
        return e.code if isinstance(e.code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
