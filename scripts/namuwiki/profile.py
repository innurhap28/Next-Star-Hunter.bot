"""Profile fields from the infobox and categories of a star document.

Only fields that came out reliably on the whole dump are kept (see docs/DATA.md):
gender, birth year, group, debut year, birthplace, agency, height.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .clean import BR, join_table_rows, lead_and_body, pre, table_cells
from .rules import strip_paren

# infobox labels we read (spaces removed: '학 력' -> '학력')
PROFILE_LABELS = (
    "본명", "예명", "출생", "출생지", "국적", "신체", "키", "학력", "데뷔", "데뷔일", "소속사",
    "소속", "소속그룹", "그룹", "포지션", "직업", "MBTI", "별명", "병역", "장르", "리더",
    "결성일", "해체일", "팬덤",
)
# labels shown in the profile chunk. 가족 and 거주지 hold private people / addresses: never.
CHUNK_LABELS = (
    "본명", "예명", "출생", "국적", "신체", "학력", "데뷔", "데뷔일", "소속사", "소속",
    "소속그룹", "그룹", "포지션", "직업", "MBTI", "별명", "병역", "장르", "리더", "결성일",
    "해체일", "팬덤",
)

ROWSPAN_RE = re.compile(r"<\|(\d+)>")
AGE_NOW_RE = re.compile(r"\s*\((?:만\s*)?\d{1,3}\s*세\)")  # '(34세)' is the age at crawl time
GENDER_CAT_RE = re.compile(r"(^|\s)(남|여)(가수|배우|성 )")
BIRTH_CAT_RE = re.compile(r"^(\d{4})년 출생$")
DEBUT_CAT_RE = re.compile(r"^(\d{4})년 데뷔$")
PLACE_CAT_RE = re.compile(r"^(.+) 출신 인물$")
YEAR_RE = re.compile(r"(\d{4})\s*년")
DATE_RE = re.compile(r"\d{4}\s*년|\d{4}[.-]\s*\d{1,2}[.-]|\d{1,2}\s*월\s*\d{1,2}\s*일")
HEIGHT_RE = re.compile(r"(\d{3}(?:\.\d)?)\s*cm")
PLACE_WORD_RE = re.compile(
    r"(특별시|광역시|특별자치시|특별자치도|[가-힣]+도|[가-힣]+시|[가-힣]+군|[가-힣]+구)(\s|$)"
)
NO_VALUE = {"없음", "-", "?", "??", "???", "미정", "불명", "비공개"}
GIRL_GROUP = "대한민국의 걸그룹"
BOY_GROUPS = ("대한민국의 보이그룹", "대한민국의 보이밴드그룹")


def profile_rows(raw_text: str, max_chars: int = 80000) -> list[tuple[str, str]]:
    """[(label, value)] from the 2-cell table rows before the first heading.

    A label cell with a row span ('||<|2> 출생 || date ||' then '|| place ||') gets the
    next one-cell rows appended to its value.
    """
    lead, _ = lead_and_body(pre(raw_text[:max_chars]))
    rows: list[tuple[str, str]] = []
    pending = 0
    for line in join_table_rows(lead.split("\n")):
        s = line.strip()
        if not s.startswith("||"):
            pending = 0
            continue
        raw_cells = [c for c in s.strip("|").split("||") if c.strip()]
        cells = table_cells(s)
        if pending and len(cells) == 1 and rows:
            rows[-1] = (rows[-1][0], rows[-1][1] + " / " + cells[0])
            pending -= 1
            continue
        pending = 0
        if len(cells) == 2 and 0 < len(cells[0]) <= 12:
            label = re.sub(r"\s+", "", cells[0])
            if label not in PROFILE_LABELS:
                continue
            value = AGE_NOW_RE.sub("", cells[1].replace(BR, " / ")).strip()
            rows.append((label, value))
            m = ROWSPAN_RE.search(raw_cells[0]) if raw_cells else None
            if m:
                pending = int(m.group(1)) - 1
    return rows


def _first(rows: Mapping[str, str], *labels: str) -> str:
    for label in labels:
        if rows.get(label):
            return rows[label]
    return ""


def _short(value: str, limit: int = 100) -> str | None:
    value = re.sub(r"\s+", " ", value).strip(" /,")
    return value[:limit] if value else None


def _year(value: str, low: int = 1900, high: int = 2030) -> int | None:
    m = YEAR_RE.search(value) or re.search(r"(\d{4})", value)
    if not m:
        return None
    year = int(m.group(1))
    return year if low <= year <= high else None


def birthplace_from(value: str) -> str | None:
    """'1992년 3월 18일 / 서울특별시 광진구' -> '서울특별시 광진구'"""
    for seg in value.split(" / "):
        seg = re.sub(r"\(.*?\)", "", seg).strip()
        if not seg:
            continue
        if DATE_RE.search(seg):
            seg = DATE_RE.split(seg)[-1].strip(" ,")
            if not PLACE_WORD_RE.search(seg):
                continue
        if PLACE_WORD_RE.search(seg) or seg.startswith("대한민국 "):
            return _short(seg)
    return None


def group_gender(categories: Iterable[str]) -> str | None:
    cats = set(categories)
    if GIRL_GROUP in cats:
        return "F"
    if cats & set(BOY_GROUPS):
        return "M"
    return None


def person_groups(categories: Iterable[str], groups: Iterable[str]) -> list[str]:
    """Groups of a person from categories: '<group>' or '<group>/멤버'."""
    names = {c[: -len("/멤버")] if c.endswith("/멤버") else c for c in categories}
    return sorted(names & set(groups))


def _aliases(title: str, rows: Mapping[str, str], redirects: Iterable[str]) -> list[str]:
    out: list[str] = []
    candidates = [strip_paren(title)]
    for label in ("본명", "예명"):
        for v in rows.get(label, "").split(" / "):
            # '전형준 (全亨俊)' -> '전형준'
            candidates.append(re.sub(r"\(.*?\)", "", v).split(",")[0])
    candidates.extend(redirects)
    for c in candidates:
        c = re.sub(r"\s+", " ", c).strip()
        # long redirects are mostly stage names from shows ('복면가왕' masks), skip them
        if (c and c != title and len(c) <= 30 and not re.search(r"[/!?,]", c)
                and c not in out):
            out.append(c)
    return out


def build_profile(
    record: Mapping,
    group_genders: Mapping[str, str | None] | None = None,
    redirects: Iterable[str] = (),
) -> tuple[dict, list[tuple[str, str]]]:
    """Profile fields for a person or group record of the extract output.

    group_genders: group title -> 'F' / 'M' / None, used for members and group lookup.
    Returns (fields, infobox rows).
    """
    title = record["title"]
    kind = record["kind"]
    cats = list(record.get("categories") or [])
    rows_list = profile_rows(record.get("text") or "")
    rows: dict[str, str] = {}
    for label, value in rows_list:
        rows.setdefault(label, value)
    groups = group_genders or {}

    birth_cat = [int(m.group(1)) for m in map(BIRTH_CAT_RE.match, cats) if m]
    debut_cat = [int(m.group(1)) for m in map(DEBUT_CAT_RE.match, cats) if m]
    place_cat = [m.group(1) for m in map(PLACE_CAT_RE.match, cats) if m]
    agency = _first(rows, "소속사", "소속").split(" / ")[0]
    agency = re.sub(r"\(.*?\)", "", agency).strip()
    if agency in NO_VALUE:
        agency = ""
    height = HEIGHT_RE.search(_first(rows, "신체", "키"))
    height_cm = float(height.group(1)) if height else None
    if height_cm is not None and not 120 <= height_cm <= 230:
        height_cm = None

    if kind == "group":
        gender = group_gender(cats)
        group_name = None
        birth_year = None
        birthplace = None
        debut_year = debut_cat[0] if debut_cat else _year(_first(rows, "데뷔일", "데뷔"))
    else:
        member_of = person_groups(cats, groups)
        found = set()
        for c in cats:
            m = GENDER_CAT_RE.search(c)
            if m and ("한국" in c or "대한민국" in c):
                found.add("M" if m.group(2) == "남" else "F")
        found |= {groups[g] for g in member_of if groups.get(g)}
        gender = found.pop() if len(found) == 1 else None  # conflicts stay empty
        group_value = _first(rows, "소속그룹", "그룹").split(" / ")[0]
        group_name = ", ".join(member_of) if member_of else _short(group_value)
        birth_year = birth_cat[0] if birth_cat else _year(_first(rows, "출생"))
        birthplace = birthplace_from(_first(rows, "출생", "출생지"))
        if not birthplace and place_cat:
            birthplace = _short(place_cat[0])
        debut_year = debut_cat[0] if debut_cat else _year(_first(rows, "데뷔"))

    fields = {
        "title": title,
        "kind": kind,
        "group_name": group_name,
        "gender": gender,
        "birth_year": birth_year,
        "debut_year": debut_year,
        "birthplace": birthplace,
        "agency": _short(agency),
        "height_cm": height_cm,
        "aliases": _aliases(title, rows, redirects),
    }
    return fields, rows_list


def profile_text(rows: Iterable[tuple[str, str]], limit: int = 1000) -> str:
    """Infobox rows as 'label: value' lines for the profile chunk (private labels skipped)."""
    lines = [f"{k}: {v}" for k, v in rows if k in CHUNK_LABELS and v]
    return "\n".join(lines)[:limit].strip()
