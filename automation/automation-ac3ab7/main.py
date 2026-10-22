import csv, io, json, os, re, sys
from datetime import datetime, timezone
from decimal import Decimal, getcontext

getcontext().prec = 100000
if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(0)

HEADER = ["sku", "name", "price", "stock"]
OUT_HEADER = ["sku", "status", "changed_fields", "old_name", "new_name", "old_price",
              "new_price", "price_delta", "old_stock", "new_stock", "stock_delta"]
PRICE_RE = re.compile(r"[0-9]+(?:\.[0-9]{1,2})?")
STOCK_RE = re.compile(r"[0-9]+")
CENT = Decimal("0.01")


class InputError(Exception):
    def __init__(self, cause, fix):
        super().__init__(cause)
        self.cause = cause
        self.fix = fix


def write_out(s):
    if sys.stdout is None:
        return
    try:
        sys.stdout.buffer.write(s.encode("utf-8"))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            sys.stdout.write(s)
        except Exception:
            pass


def fail(e):
    write_out("오류: %s\n해결: %s\n%s\n" % (e.cause, e.fix, json.dumps({"ok": False, "error": "invalid_input"})))
    return 2


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load(path, label):
    if not os.path.isfile(path):
        raise InputError("%s 파일을 찾을 수 없거나 일반 파일이 아닙니다: %s" % (label, path),
                         "존재하는 CSV 파일 경로를 지정하세요.")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as ex:
        raise InputError("%s 파일을 읽을 수 없습니다: %s" % (label, ex), "파일 권한과 경로를 확인하세요.")
    if not raw:
        raise InputError("%s 파일이 비어 있습니다." % label, "헤더와 데이터 행이 있는 CSV 파일을 사용하세요.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("%s 파일이 올바른 UTF-8이 아닙니다." % label, "파일을 UTF-8로 저장한 뒤 다시 실행하세요.")
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error as ex:
        raise InputError("%s 파일의 CSV 형식이 잘못되었습니다: %s" % (label, ex), "큰따옴표 인용을 바로잡으세요.")
    if not rows or rows[0] != HEADER:
        raise InputError("%s 파일의 첫 행이 sku,name,price,stock 이 아닙니다." % label,
                         "헤더를 공백·추가 열 없이 sku,name,price,stock 으로 고치세요.")
    if len(rows) < 2:
        raise InputError("%s 파일에 데이터 행이 없습니다." % label, "상품 데이터 행을 1개 이상 추가하세요.")
    data = {}
    for i, r in enumerate(rows[1:], start=2):
        if len(r) != 4:
            raise InputError("%s 파일 %d행의 필드가 4개가 아니거나 빈 행입니다." % (label, i),
                             "각 행을 sku,name,price,stock 4개 필드로 맞추고 빈 행을 지우세요.")
        sku, name, price, stock = [x.strip() for x in r]
        if not sku or not name:
            raise InputError("%s 파일 %d행의 sku 또는 name 이 비어 있습니다." % (label, i), "sku 와 name 을 채우세요.")
        if not PRICE_RE.fullmatch(price):
            raise InputError("%s 파일 %d행의 price 값이 잘못되었습니다: %s" % (label, i, price),
                             "price 는 0 이상의 숫자(소수 2자리까지)로 고치세요.")
        if not STOCK_RE.fullmatch(stock):
            raise InputError("%s 파일 %d행의 stock 값이 잘못되었습니다: %s" % (label, i, stock),
                             "stock 은 0 이상의 정수로 고치세요.")
        if sku in data:
            raise InputError("%s 파일 %d행의 sku 가 중복되었습니다: %s" % (label, i, sku), "중복된 sku 를 하나로 정리하세요.")
        data[sku] = (name, Decimal(price), int(stock))
    return data


def build(old, new):
    rows = []
    cnt = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    for sku in sorted(set(old) | set(new)):
        o, n = old.get(sku), new.get(sku)
        fields = ""
        pd = sd = ""
        if o is None:
            st = "added"
        elif n is None:
            st = "removed"
        else:
            ch = [k for k, a, b in zip(("name", "price", "stock"), o, n) if a != b]
            st = "changed" if ch else "unchanged"
            fields = "|".join(ch)
            pd = format((n[1] - o[1]).quantize(CENT), "f")
            sd = str(n[2] - o[2])
        cnt[st] += 1
        rows.append([sku, st, fields,
                     o[0] if o else "", n[0] if n else "",
                     format(o[1].quantize(CENT), "f") if o else "",
                     format(n[1].quantize(CENT), "f") if n else "",
                     pd, str(o[2]) if o else "", str(n[2]) if n else "", sd])
    return rows, cnt


def norm(p):
    return os.path.normcase(os.path.abspath(p))


def write_text(path, text):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def do_compare(old_path, new_path, out):
    old = load(old_path, "이전")
    new = load(new_path, "이후")
    files = [os.path.join(out, n) for n in ("comparison.csv", "summary.json", "run_log.jsonl")]
    for p in (old_path, new_path):
        for t in files:
            same = norm(p) == norm(t)
            if not same and os.path.exists(t):
                try:
                    same = os.path.samefile(p, t)
                except OSError:
                    pass
            if same:
                raise InputError("입력 파일과 결과 파일 경로가 같습니다: %s" % p,
                                 "출력 디렉터리를 입력 파일과 다른 곳으로 지정하세요.")
    rows, cnt = build(old, new)
    summary = {"ok": True, "command": "compare", "old_count": len(old), "new_count": len(new),
               "added": cnt["added"], "removed": cnt["removed"], "changed": cnt["changed"],
               "unchanged": cnt["unchanged"], "total": len(rows),
               "report_file": "comparison.csv", "run_log_file": "run_log.jsonl"}
    try:
        os.makedirs(out, exist_ok=True)
        buf = io.StringIO(newline="")
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(OUT_HEADER)
        w.writerows(rows)
        write_text(files[0], buf.getvalue())
        write_text(files[1], json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        log = {"command": "compare", "old_file": os.path.abspath(old_path), "new_file": os.path.abspath(new_path),
               "completed_at": now(), "result": "success", "total": len(rows)}
        write_text(files[2], json.dumps(log, ensure_ascii=False) + "\n")
    except OSError as ex:
        raise InputError("결과 파일을 쓸 수 없습니다: %s" % ex, "출력 디렉터리 경로와 쓰기 권한을 확인하세요.")
    return summary


DEMO = {
    "case_01": ([("A", "커피", "1000", "10"), ("B", "차", "2000", "5")],
                [("B", "차", "2000", "5"), ("C", "코코아", "3000", "8")]),
    "case_02": ([("A", "커피", "1000", "10")], [("A", "커피", "1200", "10")]),
    "case_03": ([("A", "커피", "1000", "10"), ("B", "차", "2000", "5")],
                [("A", "원두커피", "1000", "8"), ("B", "차", "2000", "5")]),
}


def csv_text(rows):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(HEADER)
    w.writerows(rows)
    return buf.getvalue()


def do_demo(out):
    recs = []
    try:
        os.makedirs(out, exist_ok=True)
        for cid, (b, a) in DEMO.items():
            d = os.path.join(out, cid)
            os.makedirs(d, exist_ok=True)
            write_text(os.path.join(d, "before.csv"), csv_text(b))
            write_text(os.path.join(d, "after.csv"), csv_text(a))
            do_compare(os.path.join(d, "before.csv"), os.path.join(d, "after.csv"), os.path.join(d, "result"))
            recs.append({"case_id": cid, "completed_at": now(), "result": "success"})
        s = {"ok": True, "command": "demo", "cases": 3, "case_ids": list(DEMO),
             "summary_file": "demo_summary.json", "run_log_file": "demo_execution.jsonl"}
        write_text(os.path.join(out, "demo_execution.jsonl"),
                   "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs))
        write_text(os.path.join(out, "demo_summary.json"), json.dumps(s, ensure_ascii=False, indent=2) + "\n")
    except OSError as ex:
        raise InputError("데모 파일을 쓸 수 없습니다: %s" % ex, "출력 디렉터리 경로와 쓰기 권한을 확인하세요.")
    return s


def parse(argv, required):
    vals = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a not in required:
            raise InputError("알 수 없는 옵션 또는 인자입니다: %s" % a,
                             "사용법: main.py compare --old <CSV> --new <CSV> --out <디렉터리> 또는 main.py demo --out <디렉터리>")
        if a in vals:
            raise InputError("옵션이 중복되었습니다: %s" % a, "각 옵션은 한 번만 지정하세요.")
        if i + 1 >= len(argv):
            raise InputError("옵션 %s 의 값이 없습니다." % a, "옵션 뒤에 값을 지정하세요.")
        vals[a] = argv[i + 1]
        i += 2
    for r in required:
        if r not in vals:
            raise InputError("필수 인자 %s 가 없습니다." % r, "%s 값을 지정하세요." % r)
    return vals


USAGE = ("사용법:\n"
         "  python main.py compare --old <이전 CSV> --new <이후 CSV> --out <출력 폴더>\n"
         "  python main.py demo --out <출력 폴더>\n"
         "  python main.py --help\n"
         "CSV 첫 행은 sku,name,price,stock 이어야 합니다.\n")


def main(argv):
    if argv in (["--help"], ["-h"]):
        write_out(USAGE)
        return 0
    try:
        if not argv or argv[0] not in ("compare", "demo"):
            raise InputError("명령이 없거나 알 수 없습니다.", "compare 또는 demo 명령을 사용하세요.")
        if argv[0] == "compare":
            v = parse(argv[1:], ["--old", "--new", "--out"])
            s = do_compare(v["--old"], v["--new"], v["--out"])
            msg = ("상품 비교 완료: 추가 %d, 삭제 %d, 변경 %d, 동일 %d (총 %d행)\n결과 파일: %s\n"
                   % (s["added"], s["removed"], s["changed"], s["unchanged"], s["total"],
                      os.path.join(v["--out"], "comparison.csv")))
        else:
            v = parse(argv[1:], ["--out"])
            s = do_demo(v["--out"])
            msg = "공개 데모 3건을 생성했습니다: %s\n" % v["--out"]
        write_out(msg + json.dumps(s, ensure_ascii=False) + "\n")
        return 0
    except InputError as e:
        return fail(e)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
