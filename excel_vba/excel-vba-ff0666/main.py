"""표 점검 데모: CSV 표의 중복 행·빈칸·형식 오류를 찾아 HTML 보고서로 만든다."""
import csv
import datetime
import html
import io
import json
import os
import re
import sys

csv.field_size_limit(100000)
USAGE = ["사용법:",
         "  python main.py check --input <CSV경로> --output-dir <결과폴더>",
         "  python main.py demo --output-dir <결과폴더>"]

HEADER = ["record_id", "name", "email", "amount", "date"]
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
AMOUNT_RE = re.compile(r"[+-]?[0-9]+(?:\.[0-9]{1,2})?")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
FORMAT_MSG = {
    "email": "이메일 형식을 확인하세요.",
    "amount": "금액 형식을 확인하세요.",
    "date": "날짜 형식을 확인하세요.",
}
COLOR_DEFAULT, COLOR_DUP, COLOR_FORMAT, COLOR_BLANK = "#ffffff", "#fff3cd", "#ffe0b2", "#ffcdd2"

DEMOS = [
    ("demo_01", [["1", "가상 고객 A", "a@example.com", "1000", "2026-01-15"],
                 ["2", "가상 고객 B", "b@example.com", "-20.50", "2026-01-16"]]),
    ("demo_02", [["1", "가상 고객 A", "a@example.com", "1000", "2026-01-15"],
                 ["1", "가상 고객 A", "a@example.com", "1000", "2026-01-15"],
                 ["2", "가상 고객 B", "b@example.com", "0", "2026-01-16"]]),
    ("demo_03", [["2", " ", "bad", "1e3", "2026-02-30"],
                 ["3", "<확인&이름>", "", "0", "2026-01-16"]]),
]


class InputError(Exception):
    def __init__(self, message, hint):
        super().__init__(message)
        self.message = message
        self.hint = hint


def emit(lines, obj):
    out = "".join(l + "\n" for l in lines) + json.dumps(obj, ensure_ascii=False) + "\n"
    stream = sys.stdout
    if stream is None:
        return
    try:
        buf = stream.buffer
        buf.write(out.encode("utf-8"))
        buf.flush()
    except AttributeError:
        stream.write(out)
        stream.flush()


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def valid_date(s):
    if not DATE_RE.fullmatch(s):
        return False
    try:
        datetime.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except ValueError:
        return False
    return True


def check_quotes(text):
    """따옴표 없는 필드 안의 큰따옴표를 거부한다."""
    state = 0  # 0 필드 시작, 1 따옴표 없는 필드, 2 따옴표 안, 3 따옴표 닫힘 직후
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if state == 0:
            if ch == '"':
                state = 2
            elif ch not in ",\r\n":
                state = 1
        elif state == 1:
            if ch == '"':
                raise InputError("따옴표로 감싸지 않은 칸 안에 큰따옴표가 있습니다.",
                                 "큰따옴표가 들어간 칸은 전체를 큰따옴표로 감싸고 안쪽 큰따옴표는 두 번(\"\") 쓰세요.")
            if ch in ",\r\n":
                state = 0
        elif state == 2:
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    i += 1
                else:
                    state = 3
        else:
            state = 0 if ch in ",\r\n" else 3
        i += 1


def protect(v):
    """엑셀에서 수식으로 읽힐 수 있는 값 앞에 작은따옴표를 붙인다."""
    if v and v[0] in "=+-@\t\r":
        try:
            float(v)
            return v
        except ValueError:
            return "'" + v
    return v


def read_table(path):
    if not os.path.exists(path):
        raise InputError("입력 파일을 찾을 수 없습니다: %s" % path,
                         "--input 경로가 맞는지 확인하고 존재하는 CSV 파일을 지정하세요.")
    if os.path.isdir(path):
        raise InputError("입력 경로가 파일이 아니라 폴더입니다: %s" % path,
                         "--input에 폴더가 아닌 CSV 파일 경로를 지정하세요.")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise InputError("입력 파일을 읽을 수 없습니다: %s" % e.strerror,
                         "파일 경로와 읽기 권한을 확인하세요.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("입력 파일이 UTF-8 인코딩이 아닙니다.",
                         "Excel에서 'CSV UTF-8(쉼표로 분리)' 형식으로 다시 저장하세요.")
    if text == "":
        raise InputError("입력 파일이 비어 있습니다.",
                         "record_id,name,email,amount,date 헤더와 데이터 행이 있는 UTF-8 CSV를 지정하세요.")
    check_quotes(text)
    try:
        records = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as e:
        if "field larger than field limit" in str(e):
            raise InputError("셀 하나가 너무 깁니다(%d자 초과)." % csv.field_size_limit(),
                             "너무 긴 셀의 내용을 줄이거나 따옴표가 닫히지 않은 곳이 없는지 확인한 뒤 다시 저장하세요.")
        raise InputError("CSV 형식이 올바르지 않습니다(닫히지 않은 큰따옴표 등).",
                         "큰따옴표가 짝에 맞게 닫혔는지 확인하고 Excel에서 UTF-8 CSV로 다시 저장하세요.")
    if not records or records[0] != HEADER:
        raise InputError("첫 줄 헤더가 record_id,name,email,amount,date 와 정확히 같지 않습니다.",
                         "열 이름과 순서를 record_id,name,email,amount,date 로 맞추고 추가·누락 열을 없애세요.")
    data = records[1:]
    if not data:
        raise InputError("헤더만 있고 데이터 행이 없습니다.",
                         "데이터 행을 한 줄 이상 추가한 뒤 다시 저장하세요.")
    for i, rec in enumerate(data, start=2):
        if len(rec) != 5:
            raise InputError("%d번째 레코드의 열 수가 %d개입니다(5개여야 함)." % (i, len(rec)),
                             "모든 행이 5개 열을 갖도록 고치고 빈 줄은 지우세요.")
    return [[c.strip() for c in rec] for rec in data]


def inspect(rows):
    """rows -> (rows_info, issues, summary). issues: (row_no, code, column, value, message)."""
    seen = set()
    infos, issues = [], []
    dup = blank = fmt = 0
    for idx, row in enumerate(rows):
        n = idx + 2
        key = tuple(row)
        is_dup = key in seen
        seen.add(key)
        row_issues = []
        blank_cols, fmt_cols = set(), set()
        if is_dup:
            dup += 1
            row_issues.append((n, "DUPLICATE", "*", "", "앞선 행과 모든 값이 같습니다."))
        for c, name in enumerate(HEADER):
            if row[c] == "":
                blank += 1
                blank_cols.add(name)
                row_issues.append((n, "BLANK", name, "", "필수 값이 비어 있습니다."))
        for c, name in enumerate(HEADER):
            v = row[c]
            if v == "":
                continue
            ok = True
            if name == "email":
                ok = bool(EMAIL_RE.fullmatch(v))
            elif name == "amount":
                ok = bool(AMOUNT_RE.fullmatch(v))
            elif name == "date":
                ok = valid_date(v)
            if not ok:
                fmt += 1
                fmt_cols.add(name)
                row_issues.append((n, "FORMAT", name, v, FORMAT_MSG[name]))
        issues.extend(row_issues)
        infos.append((n, row, is_dup, blank_cols, fmt_cols, row_issues))
    summary = {"input_rows": len(rows), "duplicate_rows": dup, "blank_cells": blank,
               "format_errors": fmt, "issue_count": dup + blank + fmt}
    return infos, issues, summary


def build_html(infos, summary):
    e = html.escape
    p = []
    p.append('<!DOCTYPE html>\n<html lang="ko"><head><meta charset="utf-8">'
             '<title>표 점검 보고서</title>\n<style>body{font-family:sans-serif}'
             'table{border-collapse:collapse}td,th{border:1px solid #999;padding:4px 8px}'
             'th{background:#eeeeee}.lg{display:inline-block;padding:2px 10px;margin-right:6px;'
             'border:1px solid #999}</style></head><body>\n<h1>표 점검 보고서</h1>\n')
    p.append("<p>입력 행 %d · 중복 행 %d · 빈칸 %d · 형식 오류 %d · 문제 합계 %d</p>\n" % (
        summary["input_rows"], summary["duplicate_rows"], summary["blank_cells"],
        summary["format_errors"], summary["issue_count"]))
    p.append('<div id="legend"><strong>범례</strong> '
             '<span class="lg" style="background-color:%s">중복 행</span>'
             '<span class="lg" style="background-color:%s">빈칸</span>'
             '<span class="lg" style="background-color:%s">형식 오류</span></div>\n' % (
                 COLOR_DUP, COLOR_BLANK, COLOR_FORMAT))
    p.append('<table id="results">\n<thead><tr>')
    for h in ["row_number"] + HEADER + ["issues"]:
        p.append("<th>%s</th>" % h)
    p.append("</tr></thead>\n<tbody>\n")
    for n, row, is_dup, bcols, fcols, rissues in infos:
        p.append('<tr data-row="%d"><td data-column="row_number">%d</td>' % (n, n))
        for c, name in enumerate(HEADER):
            if name in bcols:
                color = COLOR_BLANK
            elif name in fcols:
                color = COLOR_FORMAT
            elif is_dup:
                color = COLOR_DUP
            else:
                color = COLOR_DEFAULT
            p.append('<td data-column="%s" style="background-color:%s">%s</td>' % (name, color, e(row[c])))
        text = " | ".join("%s:%s" % (i[1], i[2]) for i in rissues)
        p.append('<td data-column="issues">%s</td></tr>\n' % e(text))
    p.append("</tbody>\n</table>\n</body></html>\n")
    return "".join(p)


def same_path(a, b):
    try:
        if os.path.exists(a) and os.path.exists(b):
            return os.path.samefile(a, b)
    except OSError:
        pass
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def run_check(input_path, output_dir, argv):
    started = utc_now()
    in_abs = os.path.abspath(input_path)
    out_abs = os.path.abspath(output_dir)
    files = {"report_html": os.path.join(out_abs, "report.html"),
             "issues_csv": os.path.join(out_abs, "issues.csv"),
             "run_json": os.path.join(out_abs, "run.json")}
    for f in files.values():
        if same_path(in_abs, f):
            raise InputError("입력 파일과 출력 파일 경로가 겹칩니다: %s" % f,
                             "--output-dir 를 입력 CSV가 없는 다른 폴더로 지정하세요.")
    rows = read_table(in_abs)
    infos, issues, summary = inspect(rows)
    try:
        if os.path.exists(out_abs) and not os.path.isdir(out_abs):
            raise InputError("출력 경로가 폴더가 아닙니다: %s" % out_abs,
                             "--output-dir 에 폴더 경로를 지정하세요.")
        os.makedirs(out_abs, exist_ok=True)
        with open(files["report_html"], "w", encoding="utf-8", newline="") as f:
            f.write(build_html(infos, summary))
        with open(files["issues_csv"], "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, lineterminator="\r\n")
            w.writerow(["row_number", "code", "column", "value", "message"])
            for it in issues:
                it = list(it)
                it[3] = protect(it[3])
                w.writerow(it)
        run = {"command": "check", "argv": list(argv), "input_file": in_abs,
               "output_dir": out_abs, "started_at": started, "finished_at": utc_now(),
               "summary": summary}
        with open(files["run_json"], "w", encoding="utf-8", newline="") as f:
            json.dump(run, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        raise InputError("출력 폴더에 쓸 수 없습니다: %s" % (e.strerror or e),
                         "--output-dir 경로가 올바르고 쓰기 권한이 있는지 확인하세요.")
    return in_abs, out_abs, summary, files


def parse_args(argv, allowed):
    opts = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a not in allowed:
            raise InputError("알 수 없는 옵션 또는 인자입니다: %s" % a,
                             "사용 가능한 옵션: %s" % ", ".join(allowed))
        if a in opts:
            raise InputError("옵션이 중복되었습니다: %s" % a, "각 옵션은 한 번만 지정하세요.")
        if i + 1 >= len(argv) or argv[i + 1].startswith("--") or argv[i + 1] == "":
            raise InputError("옵션 값이 없습니다: %s" % a, "%s 뒤에 경로를 붙여 지정하세요." % a)
        opts[a] = argv[i + 1]
        i += 2
    for a in allowed:
        if a not in opts:
            raise InputError("필수 옵션이 빠졌습니다: %s" % a, "%s <경로> 옵션을 추가하세요." % a)
    return opts


def cmd_check(args):
    opts = parse_args(args, ["--input", "--output-dir"])
    in_abs, out_abs, s, files = run_check(opts["--input"], opts["--output-dir"], ["check"] + args)
    lines = ["표 점검을 마쳤습니다: 입력 %d행, 중복 %d행, 빈칸 %d칸, 형식 오류 %d건 (문제 합계 %d건)." % (
        s["input_rows"], s["duplicate_rows"], s["blank_cells"], s["format_errors"], s["issue_count"]),
        "결과 폴더: %s" % out_abs]
    obj = {"command": "check", "status": "ok"}
    obj.update(s)
    obj["output_dir"] = out_abs
    obj["files"] = files
    emit(lines, obj)


def cmd_demo(args):
    opts = parse_args(args, ["--output-dir"])
    out_abs = os.path.abspath(opts["--output-dir"])
    try:
        if os.path.exists(out_abs) and not os.path.isdir(out_abs):
            raise InputError("출력 경로가 폴더가 아닙니다: %s" % out_abs,
                             "--output-dir 에 폴더 경로를 지정하세요.")
        os.makedirs(out_abs, exist_ok=True)
    except OSError as e:
        raise InputError("출력 폴더를 만들 수 없습니다: %s" % (e.strerror or e),
                         "--output-dir 경로가 올바르고 쓰기 권한이 있는지 확인하세요.")
    demos, lines = [], []
    for did, data in DEMOS:
        csv_path = os.path.join(out_abs, did + ".csv")
        sub = os.path.join(out_abs, did)
        try:
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow(HEADER)
                w.writerows(data)
        except OSError as e:
            raise InputError("데모 CSV를 쓸 수 없습니다: %s" % (e.strerror or e),
                             "--output-dir 경로의 쓰기 권한을 확인하세요.")
        in_abs, sub_abs, s, files = run_check(
            csv_path, sub, ["check", "--input", csv_path, "--output-dir", sub])
        demos.append({"id": did, "input_file": in_abs, "output_dir": sub_abs,
                      "summary": s, "files": files})
        lines.append("%s: 입력 %d행, 중복 %d행, 빈칸 %d칸, 형식 오류 %d건" % (
            did, s["input_rows"], s["duplicate_rows"], s["blank_cells"], s["format_errors"]))
    manifest = os.path.join(out_abs, "manifest.json")
    try:
        with open(manifest, "w", encoding="utf-8", newline="") as f:
            json.dump({"demos": demos}, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except OSError as e:
        raise InputError("manifest.json 을 쓸 수 없습니다: %s" % (e.strerror or e),
                         "--output-dir 경로의 쓰기 권한을 확인하세요.")
    lines.insert(0, "가상 데이터 데모 3건을 만들고 점검했습니다.")
    emit(lines, {"command": "demo", "status": "ok", "demo_count": 3,
                 "output_dir": out_abs, "manifest_file": manifest})


def main(argv):
    try:
        if not argv:
            raise InputError("명령이 없습니다.", "check 또는 demo 명령을 지정하세요. 예: python main.py demo --output-dir out")
        if argv[0] in ("--help", "-h", "help"):
            emit(USAGE, {"command": "help", "status": "ok"})
        elif argv[0] == "check":
            cmd_check(argv[1:])
        elif argv[0] == "demo":
            cmd_demo(argv[1:])
        else:
            raise InputError("알 수 없는 명령입니다: %s" % argv[0],
                             "사용 가능한 명령은 check 와 demo 두 개입니다.")
        return 0
    except InputError as e:
        emit(["오류: %s" % e.message, "해결 방법: %s" % e.hint],
             {"status": "error", "error": "INVALID_INPUT", "message": e.message, "hint": e.hint})
        return 2
    except Exception as e:  # 예기치 못한 오류도 traceback 없이 안내
        msg = "처리 중 예기치 못한 오류가 발생했습니다."
        hint = "입력 경로와 UTF-8 CSV 형식, 필수 옵션을 다시 확인하세요."
        emit(["오류: %s" % msg, "해결 방법: %s" % hint],
             {"status": "error", "error": "INVALID_INPUT", "message": msg, "hint": hint})
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
