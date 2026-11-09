"""税関の輸入統計品目表（実行関税率表）と輸出統計品目表を読む。

どちらも類ごとの HTML（Shift_JIS）で、改正のたびに日付のフォルダ（2026_10_31 など）で
出る。一覧のページから最新の日付を 1 つ決め、類ごとのページの表を 1 行 1 品目の CSV にする。

- 類（2桁）・項（4桁、01.01）・号（6桁、0101.21）・統計細分（9桁）の行を出す
- コードの無い行（「馬」「2 その他のもの」など）は見出しで、下の品目の full_name に入る
- 字下げの深さは、輸入は padding-left の em、輸出は品名の先頭の「－」の数で表される

出力:
- data/customs/import_item.csv
- data/customs/export_item.csv

データソース: 税関 輸入統計品目表 https://www.customs.go.jp/tariff/index.htm
             輸出統計品目表 https://www.customs.go.jp/yusyutu/index.htm
"""

import csv
import html
import logging
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

logger = logging.getLogger("pipelines")

OUTPUT_DIR = Path("data/customs")
BASE = "https://www.customs.go.jp"
INDEXES = {"import_item": "/tariff/index.htm", "export_item": "/yusyutu/index.htm"}
FIELDS = [
    "edition",
    "level",
    "code",
    "hs_code",
    "parent_code",
    "chapter_code",
    "name",
    "full_name",
    "unit_1",
    "unit_2",
    "source_url",
]


def fetch(url: str) -> str:
    for attempt in range(5):
        try:
            req = Request(url, headers={"User-Agent": "dataset-customs"})
            with urlopen(req, timeout=60) as resp:
                return resp.read().decode("cp932", errors="replace")
        except (HTTPError, URLError, TimeoutError, ConnectionResetError) as e:
            if isinstance(e, HTTPError) and e.code < 500 or attempt == 4:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def text(cell: str) -> str:
    s = re.sub(r"<br\s*/?>", " ", cell, flags=re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def latest_edition(index_url: str) -> tuple[str, str]:
    """一覧のページから最新の日付のフォルダを返す（("2026_10_31", そのページの URL)）。"""
    page = fetch(BASE + index_url)
    dates = sorted(set(re.findall(r'href="(\d{4}(?:_\d{1,2}_\d{1,2}|_\d+)?)/index\.html?"', page)))
    if not dates:
        raise SystemExit(f"{index_url} に日付のフォルダが無い")
    edition = max(dates, key=lambda d: [int(n) for n in d.split("_")])
    return edition, urljoin(BASE + index_url, f"{edition}/index.htm")


def chapter_urls(edition_url: str) -> list[str]:
    page = fetch(edition_url)
    links = sorted(set(re.findall(r'href="(data/j_\d{2}\.htm)"', page)))
    if len(links) < 90:
        raise SystemExit(f"{edition_url} の類のページが {len(links)} しか無い")
    return [urljoin(edition_url, link) for link in links]


def depth(attrs: str, name: str) -> int:
    m = re.search(r"padding-left:\s*(\d+)em", attrs)
    dashes = len(re.match(r"[－-]*", name).group(0))
    return int(m.group(1)) if m and int(m.group(1)) else dashes


def chapter_rows(page: str, edition: str, url: str) -> list[dict]:
    """1 つの類のページを読み、類・項・号・統計細分の行を返す。"""
    m = re.search(r"第(\d+)類[\s　]*([^<]+)", page)
    if not m:
        raise SystemExit(f"{url} に類の見出しが無い")
    chapter = f"{int(m.group(1)):02d}"
    chapter_name = text(m.group(2))
    rows = [
        {
            "level": "chapter",
            "code": chapter,
            "hs_code": chapter,
            "parent_code": None,
            "name": chapter_name,
            "full_name": chapter_name,
            "unit_1": None,
            "unit_2": None,
        }
    ]
    heading = subheading = None
    stack: list[tuple[int, str]] = []  # (字下げ, 品名) の祖先
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S):
        tds = re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S)
        if len(tds) < 6:
            continue
        hs, stat = text(tds[0][1]), text(tds[1][1])
        if not re.fullmatch(r"(\d{2}\.\d{2}|\d{4}\.\d{2})?", hs) or not re.fullmatch(
            r"(\d{3})?", stat
        ):
            continue
        raw_name = text(tds[2][1])
        # 号に分かれない項（85.03 など）は項の行の品名が空で、品名は号の行にある
        if not raw_name and not hs:
            continue
        level_depth = depth(tds[2][0], raw_name)
        name = raw_name.lstrip("－- ").strip()
        while stack and stack[-1][0] >= level_depth:
            stack.pop()
        full_name = " ＞ ".join([n for _, n in stack] + [name]) if name else None
        if name:
            stack.append((level_depth, name))
        units = (text(tds[-3][1]) or None, text(tds[-2][1]) or None)

        if re.fullmatch(r"\d{2}\.\d{2}", hs):
            heading, subheading = hs.replace(".", ""), None
            if heading[:2] != chapter:
                raise SystemExit(f"{url} の項 {hs} が類 {chapter} に無い")
            rows.append(_row("heading", heading, heading, chapter, name or None, full_name, (None, None)))
            # 号に分かれない項（01.05 などの 4 桁のまま統計細分を持つもの）は 6 桁の号を 00 で埋める
            if stat:
                subheading = heading + "00"
                rows.append(_row("statistical", subheading + stat, subheading, heading, name, full_name, units))
            continue
        if hs:
            subheading = hs.replace(".", "")
            if heading is None or subheading[:4] != heading:
                raise SystemExit(f"{url} の号 {hs} が項 {heading} の下に無い")
            rows.append(_row("subheading", subheading, subheading, heading, name, full_name, (None, None)))
        if stat:
            if subheading is None:
                raise SystemExit(f"{url} の統計細分 {stat} の前に号が無い")
            code = subheading + stat
            # 輸入の時期で税率が分かれる品目（0803.10 の 100 など）は同じ統計番号が続けて
            # 複数の行に出る。1 品目にまとめ、品名は時期の行の 1 つ上の見出しにする
            if rows[-1]["code"] == code:
                parent_path = rows[-1]["full_name"].rsplit(" ＞ ", 1)[0]
                rows[-1] |= {"name": parent_path.rsplit(" ＞ ", 1)[-1], "full_name": parent_path}
                continue
            rows.append(_row("statistical", code, subheading, subheading, name, full_name, units))
    # 品名の空の項は、その下の号の品名を使う
    first_child = {}
    for r in rows:
        first_child.setdefault(r["parent_code"], r)
    rows = [
        r | {"name": first_child[r["code"]]["name"], "full_name": first_child[r["code"]]["name"]}
        if r["level"] == "heading" and not r["name"]
        else r
        for r in rows
    ]
    return [
        r | {"edition": edition.replace("_", "-"), "chapter_code": chapter, "source_url": url}
        for r in rows
    ]


def _row(level, code, hs_code, parent, name, full_name, units) -> dict:
    return {
        "level": level,
        "code": code,
        "hs_code": hs_code,
        "parent_code": parent,
        "name": name,
        "full_name": full_name,
        "unit_1": units[0],
        "unit_2": units[1],
    }


def check(table: str, rows: list[dict]) -> None:
    codes = [r["code"] for r in rows]
    dup = {c for c in codes if codes.count(c) > 1} if len(set(codes)) != len(codes) else set()
    if dup:
        raise SystemExit(f"{table} でコードが重複: {sorted(dup)[:10]}")
    known = set(codes)
    orphans = [r["code"] for r in rows if r["parent_code"] and r["parent_code"] not in known]
    if orphans:
        raise SystemExit(f"{table} で親の無いコード: {orphans[:10]}")


def download_customs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for table, index_url in INDEXES.items():
        edition, edition_url = latest_edition(index_url)
        logger.info(f"  {table}: {edition}")
        rows = [
            row
            for url in chapter_urls(edition_url)
            for row in chapter_rows(fetch(url), edition, url)
        ]
        check(table, rows)
        logger.info(f"  {table}: {len(rows)} rows")
        with (OUTPUT_DIR / f"{table}.csv").open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
