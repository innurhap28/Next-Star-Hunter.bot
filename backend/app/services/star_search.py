"""Find stars in star_profiles / star_chunks for a chat question.

Rule-based: the question is split into structured conditions (birthplace, gender, idol /
actor / singer, debut or birth year, group or star names, height order) and the rest are
content keywords. Keywords are searched only inside the chunks of the stars that passed
the structured filters, so no full-text index on the chunk text is needed.

search_stars() never raises. A missing or empty table or any DB error gives an empty
result and a star_search_failure log line.
"""
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import and_, func, literal, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from ..models import StarChunk, StarProfile

logger = logging.getLogger("next_star_hunter")

MAX_STARS = 5
MAX_SNIPPETS = 2
SNIPPET_CHARS = 300
CANDIDATE_LIMIT = 300  # stars whose chunks are scanned for keywords
MEMBER_LIMIT = 20
STATEMENT_TIMEOUT_MS = 250  # PostgreSQL only; a slow query becomes an empty result
FALLBACK_TIMEOUT_MS = 150
PROFILE_SECTION = "프로필"

# region word -> birthplace prefixes as written in the data ('부산광역시 해운대구', '경상남도 …')
REGIONS: dict[str, tuple[str, ...]] = {
    "서울": ("서울",), "부산": ("부산",), "대구": ("대구",), "인천": ("인천",),
    "광주": ("광주",), "대전": ("대전",), "울산": ("울산",), "세종": ("세종",),
    "제주": ("제주",), "경기": ("경기",), "강원": ("강원",),
    "충청": ("충청", "충북", "충남"), "충북": ("충청북도", "충북"), "충남": ("충청남도", "충남"),
    "전라": ("전라", "전북", "전남"), "전북": ("전라북도", "전북"), "전남": ("전라남도", "전남"),
    "경상": ("경상", "경북", "경남"), "경북": ("경상북도", "경북"), "경남": ("경상남도", "경남"),
    "수원": ("경기도 수원",), "성남": ("경기도 성남",), "고양": ("경기도 고양",),
    "용인": ("경기도 용인",), "부천": ("경기도 부천",), "안양": ("경기도 안양",),
    "청주": ("충청북도 청주",), "천안": ("충청남도 천안",), "전주": ("전라북도 전주",),
    "포항": ("경상북도 포항",), "창원": ("경상남도 창원",), "김해": ("경상남도 김해",),
    "춘천": ("강원도 춘천", "강원특별자치도 춘천"), "원주": ("강원도 원주", "강원특별자치도 원주"),
}
REGION_ALIASES = {
    "충청도": "충청", "전라도": "전라", "경상도": "경상", "경기도": "경기", "강원도": "강원",
    "제주도": "제주", "충청북도": "충북", "충청남도": "충남", "전라북도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
}
GENDER_WORDS = {
    "남자": "M", "남성": "M", "남배우": "M", "남가수": "M", "남돌": "M", "보이그룹": "M",
    "여자": "F", "여성": "F", "여배우": "F", "여가수": "F", "여돌": "F", "걸그룹": "F",
}
# kind word -> 'idol' | 'actor' | 'singer'
KIND_WORDS = {
    "아이돌": "idol", "남돌": "idol", "여돌": "idol", "걸그룹": "idol", "보이그룹": "idol",
    "배우": "actor", "연기자": "actor", "남배우": "actor", "여배우": "actor",
    "멤버": "idol", "가수": "singer", "남가수": "singer", "여가수": "singer", "솔로가수": "singer",
}
SIMILAR_WORDS = ("비슷한", "비슷하", "닮은", "느낌의", "스타일의", "같은 느낌")
TALL_RE = re.compile(r"키\s*(?:가|는)?\s*(큰|크고|큰데|장신)|장신")
SHORT_RE = re.compile(r"키\s*(?:가|는)?\s*(작은|작고)")
DEBUT_RE = re.compile(r"(\d{4}|\d{2})\s*년\s*(?:도)?\s*(?:에\s*)?데뷔"
                      r"|데뷔\s*(?:연도|년도)?\s*(?:가|는)?\s*(\d{4})")
BIRTH_RE = re.compile(r"(\d{4}|\d{2})\s*년\s*생|(\d{4})\s*년\s*(?:에\s*)?(?:출생|태어난)")
DECADE_BIRTH_RE = re.compile(r"(\d{2}|\d{4})\s*년대\s*생")
JOSA = ("이랑", "에서", "에게", "처럼", "하고", "까지", "부터", "보다", "으로", "이나",
        "랑", "와", "과", "은", "는", "이", "가", "을", "를", "의", "에", "도", "만", "로", "나")
STOPWORDS = {
    "추천", "추천해", "추천해줘", "추천해주세요", "알려줘", "알려주세요", "알려", "소개",
    "소개해줘",
    "누구", "누가", "있어", "있나", "있을까", "있는", "있고", "없는", "사람", "스타", "연예인",
    "중에", "중", "출신", "키가", "키는", "쓴", "쓰는", "끼는", "낀", "한", "하는", "된", "좀",
    "그",
    "그리고", "또", "더", "제일", "가장", "많이", "조금", "같은", "비슷한", "닮은", "느낌",
    "데뷔", "데뷔한", "태어난", "생", "키", "큰", "작은", "장신", "명", "해줘", "줘", "찾아줘",
    "보여줘", "어때", "뭐야", "어떤", "누구야", "좋아", "좋은", "그룹", "팀", "솔로",
    "요즘", "최근", "인기", "유명한", "분", "애", "친구", "대해", "얘기", "정보", "주세요",
}
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")


@dataclass
class Query:
    regions: list[str] = field(default_factory=list)  # keys of REGIONS
    gender: Optional[str] = None  # 'M' | 'F'
    kinds: list[str] = field(default_factory=list)  # 'idol' | 'actor' | 'singer'
    debut_years: Optional[tuple[int, int]] = None
    birth_years: Optional[tuple[int, int]] = None
    height_order: Optional[str] = None  # 'desc' | 'asc'
    similar: bool = False
    inherited: bool = False  # structured conditions came from the previous question
    tokens: list[str] = field(default_factory=list)  # name candidates (with josa variants)
    keywords: list[str] = field(default_factory=list)

    def structured(self) -> bool:
        return bool(self.regions or self.gender or self.kinds or self.debut_years
                    or self.birth_years or self.height_order)


@dataclass
class StarSearchResult:
    stars: list[dict] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        return [s["title"] for s in self.stars]


def _year(text_value: str) -> int:
    year = int(text_value)
    if year < 100:
        year += 2000 if year <= 30 else 1900
    return year


def strip_josa(token: str) -> str:
    for josa in JOSA:
        if token.endswith(josa) and len(token) - len(josa) >= 2:
            return token[: -len(josa)]
    return token


def parse_query(message: str) -> Query:
    """Structured conditions and leftover keywords from a Korean question."""
    q = Query()
    text_value = message.strip()
    m = DEBUT_RE.search(text_value)
    if m:
        year = _year(m.group(1) or m.group(2))
        q.debut_years = (year, year)
    m = DECADE_BIRTH_RE.search(text_value)
    if m:
        start = _year(m.group(1)[-2:]) if len(m.group(1)) == 2 else int(m.group(1))
        q.birth_years = (start, start + 9)
    else:
        m = BIRTH_RE.search(text_value)
        if m:
            year = _year(m.group(1) or m.group(2))
            q.birth_years = (year, year)
    if TALL_RE.search(text_value):
        q.height_order = "desc"
    elif SHORT_RE.search(text_value):
        q.height_order = "asc"
    q.similar = any(w in text_value for w in SIMILAR_WORDS)

    for raw in TOKEN_RE.findall(text_value):
        if raw.isdigit() or re.fullmatch(r"\d+(년|년대|년생|년도|cm)\w*", raw):
            continue
        word = strip_josa(raw)
        found = False
        for w in (raw, word):
            region = REGION_ALIASES.get(w, w)
            if region in REGIONS:
                if region not in q.regions:
                    q.regions.append(region)
                found = True
            if w in GENDER_WORDS:
                q.gender = GENDER_WORDS[w]
                found = True
            if w in KIND_WORDS:
                if KIND_WORDS[w] not in q.kinds:
                    q.kinds.append(KIND_WORDS[w])
                found = True
            if found:
                break
        if found:
            continue
        # region + 출신 written together ('부산출신')
        if word.endswith("출신") and word[:-2] in REGIONS:
            q.regions.append(word[:-2])
            continue
        if raw in STOPWORDS or word in STOPWORDS or raw.startswith(("추천", "알려", "데뷔")):
            continue
        for w in (raw, word):
            if w not in q.tokens:
                q.tokens.append(w)
        if len(word) >= 2 and not word.endswith(("한", "는", "은", "운", "줘", "요", "게", "고")):
            q.keywords.append(word)
    return q


def merge_previous(current: Query, previous: Query) -> Query:
    """A follow-up with no conditions or names keeps the previous structured conditions."""
    current.regions = current.regions or previous.regions
    current.gender = current.gender or previous.gender
    current.kinds = current.kinds or previous.kinds
    current.debut_years = current.debut_years or previous.debut_years
    current.birth_years = current.birth_years or previous.birth_years
    current.height_order = current.height_order or previous.height_order
    current.inherited = current.structured()
    return current


def _use_chunk_index(conn, on=True):
    """Make PostgreSQL read star_chunks through the (profile_id, chunk_index) index.

    Row estimates for the profile-chunk join and for long id lists are low, so the
    planner picks a full scan of star_chunks (230MB) that takes 250ms+ on the full data.
    """
    if conn.dialect.name == "postgresql":
        conn.execute(text("SET LOCAL enable_seqscan = " + ("off" if on else "on")))


def _alias_match(name):
    wrapped = literal("\n") + StarProfile.aliases + literal("\n")
    return wrapped.like("%\n" + name.replace("%", "").replace("_", "") + "\n%")


def _find_named(conn, tokens: list[str]) -> list[dict]:
    """Profiles whose title or one of the aliases equals a token (exact match)."""
    tokens = [t for t in tokens if len(t) >= 2][:12]
    if not tokens:
        return []
    cond = or_(StarProfile.title.in_(tokens), *[_alias_match(t) for t in tokens])
    rows = conn.execute(select(StarProfile.__table__).where(cond).limit(10)).mappings().all()
    # a matched name may be a word that is also a keyword; keep the most specific ones
    return [dict(r) for r in rows]


def _structured_filters(q: Query, chunks_alias):
    conds = []
    if q.regions:
        prefixes = [p for r in q.regions for p in REGIONS[r]]
        place = func.coalesce(StarProfile.birthplace, "")
        conds.append(or_(*[place.like(p + "%") for p in prefixes],
                         *[place.like("대한민국 " + p + "%") for p in prefixes]))
    if q.gender:
        conds.append(StarProfile.gender == q.gender)
    if q.debut_years:
        conds.append(StarProfile.debut_year.between(*q.debut_years))
    if q.birth_years:
        conds.append(StarProfile.birth_year.between(*q.birth_years))
    if q.height_order:
        conds.append(StarProfile.height_cm.isnot(None))
    kind_conds = []
    for kind in q.kinds:
        if kind == "idol":
            kind_conds.append(StarProfile.group_name.isnot(None))
        elif kind == "actor":
            kind_conds.append(chunks_alias.content.like("%배우%"))
        elif kind == "singer":
            kind_conds.append(chunks_alias.content.like("%가수%"))
    if kind_conds:
        conds.append(or_(*kind_conds))
    conds.append(StarProfile.kind == "person")
    return conds


def _candidates(conn, q: Query, extra=None, exclude=()) -> list[dict]:
    """Person profiles that pass the structured filters (bounded, best documented first)."""
    prof_chunk = StarChunk.__table__.alias("pc")
    joined = StarProfile.__table__.outerjoin(
        prof_chunk, and_(prof_chunk.c.profile_id == StarProfile.id,
                         prof_chunk.c.chunk_index == 0,
                         prof_chunk.c.section == PROFILE_SECTION))
    conds = _structured_filters(q, prof_chunk.c)
    if extra is not None:
        conds.append(extra)
    if exclude:
        conds.append(StarProfile.id.notin_(list(exclude)))
    _use_chunk_index(conn, bool(set(q.kinds) & {"actor", "singer"}))
    stmt = select(StarProfile.__table__).select_from(joined).where(and_(*conds))
    if q.height_order == "desc":
        stmt = stmt.order_by(StarProfile.height_cm.desc(), StarProfile.id)
    elif q.height_order == "asc":
        stmt = stmt.order_by(StarProfile.height_cm.asc(), StarProfile.id)
    else:
        # more chunks = a longer document = usually a better known star
        size = (select(func.count()).select_from(StarChunk.__table__)
                .where(StarChunk.profile_id == StarProfile.id).scalar_subquery())
        stmt = stmt.order_by(size.desc(), StarProfile.id)
    return [dict(r) for r in conn.execute(stmt.limit(CANDIDATE_LIMIT)).mappings().all()]


def _keyword_hits(conn, profile_ids: list[int], keywords: list[str]) -> dict[int, list]:
    """profile_id -> [(section, content, keyword)] for chunks containing a keyword."""
    if not profile_ids or not keywords:
        return {}
    _use_chunk_index(conn)
    rows = conn.execute(
        select(StarChunk.profile_id, StarChunk.section, StarChunk.content)
        .where(StarChunk.profile_id.in_(profile_ids),
               or_(*[StarChunk.content.like("%" + k + "%") for k in keywords]))
        .order_by(StarChunk.profile_id, StarChunk.chunk_index)
    ).all()
    out: dict[int, list] = {}
    for pid, section, content in rows:
        kw = next((k for k in keywords if k in content), "")
        out.setdefault(pid, []).append((section, content, kw))
    return out


def _bounded_keyword_search(conn, keywords: list[str]) -> dict[int, list]:
    """No structured conditions: a LIMITed scan over all chunks for the keywords."""
    if not keywords:
        return {}
    _use_chunk_index(conn, False)
    if conn.dialect.name == "postgresql":
        # a full scan; keep it short so the whole search stays well under 300ms
        conn.execute(text(f"SET LOCAL statement_timeout = {FALLBACK_TIMEOUT_MS}"))
    try:
        rows = conn.execute(
            select(StarChunk.profile_id, StarChunk.section, StarChunk.content)
            .where(and_(*[StarChunk.content.like("%" + k + "%") for k in keywords]))
            .limit(40)
        ).all()
    except OperationalError:
        # a rare word scans the whole table and hits statement_timeout: treat as not found
        logger.info("star_search_fallback_timeout")
        return {}
    out: dict[int, list] = {}
    for pid, section, content in rows:
        out.setdefault(pid, []).append((section, content, keywords[0]))
    return out


def _snippet(content: str, keyword: str = "") -> str:
    content = re.sub(r"\s+", " ", content).strip()
    if len(content) <= SNIPPET_CHARS:
        return content
    pos = content.find(keyword) if keyword else -1
    start = max(0, pos - SNIPPET_CHARS // 3) if pos > 0 else 0
    piece = content[start:start + SNIPPET_CHARS].strip()
    return ("…" if start else "") + piece + "…"


def _default_snippets(conn, profile_ids: list[int]) -> dict[int, list]:
    """The profile chunk and the first text chunk of each star."""
    if not profile_ids:
        return {}
    _use_chunk_index(conn)
    rows = conn.execute(
        select(StarChunk.profile_id, StarChunk.section, StarChunk.content)
        .where(StarChunk.profile_id.in_(profile_ids), StarChunk.chunk_index < MAX_SNIPPETS)
        .order_by(StarChunk.profile_id, StarChunk.chunk_index)
    ).all()
    out: dict[int, list] = {}
    for pid, section, content in rows:
        out.setdefault(pid, []).append((section, content, ""))
    return out


def _members(conn, group_title: str) -> list[str]:
    names = conn.execute(
        select(StarProfile.title).where(
            StarProfile.kind == "person",
            or_(StarProfile.group_name == group_title,
                StarProfile.group_name.like(group_title + ", %"),
                StarProfile.group_name.like("%, " + group_title)))
        .order_by(StarProfile.id).limit(MEMBER_LIMIT)
    ).scalars().all()
    return list(names)


def _star(row: dict, snippets: list, members: Optional[list[str]] = None) -> dict:
    star = {k: row.get(k) for k in ("title", "kind", "group_name", "gender", "birth_year",
                                    "debut_year", "birthplace", "agency", "height_cm",
                                    "source_url")}
    star["snippets"] = [{"section": s, "text": _snippet(c, k)} for s, c, k in
                        snippets[:MAX_SNIPPETS]]
    if members:
        star["members"] = members
    return star


def _search(conn, q: Query) -> StarSearchResult:
    result = StarSearchResult()
    named = _find_named(conn, q.tokens)
    named_titles = {r["title"] for r in named}
    # words that turned out to be names are not content keywords
    name_words = set(named_titles)
    for r in named:
        name_words.update((r.get("aliases") or "").split("\n"))
    keywords = [k for k in q.keywords if k not in name_words][:3]
    named = named[:3]

    chosen: list[tuple[dict, list, Optional[list[str]]]] = []
    groups = [r for r in named if r["kind"] == "group"]
    persons = [r for r in named if r["kind"] == "person"]

    if groups:
        # '트와이스 멤버' / '트와이스에서 키 큰 멤버': the group and its members
        group = groups[0]
        members = _members(conn, group["title"])
        chosen.append((group, [], members))
        if members:
            q_members = Query(gender=q.gender, debut_years=q.debut_years,
                              birth_years=q.birth_years, height_order=q.height_order,
                              regions=q.regions)
            rows = _candidates(conn, q_members, extra=StarProfile.title.in_(members))
            hits = _keyword_hits(conn, [r["id"] for r in rows], keywords)
            if keywords:
                rows = [r for r in rows if r["id"] in hits] or rows
            for r in rows[: MAX_STARS - 1]:
                chosen.append((r, hits.get(r["id"], []), None))
    elif persons and q.similar:
        # '아이유랑 비슷한 가수': the named star, then stars with the same gender and kind
        base = persons[0]
        chosen.append((base, [], None))
        sim = Query(regions=q.regions, kinds=q.kinds or ["singer"],
                    gender=q.gender or base.get("gender"), birth_years=q.birth_years,
                    height_order=q.height_order)
        debut = base.get("debut_year")
        if not q.debut_years and debut:
            sim.debut_years = (debut - 3, debut + 3)
        else:
            sim.debut_years = q.debut_years
        if base.get("group_name") is None and "idol" not in sim.kinds:
            extra = StarProfile.group_name.is_(None)
        else:
            extra = None
        rows = _candidates(conn, sim, extra=extra, exclude=[base["id"]])
        hits = _keyword_hits(conn, [r["id"] for r in rows], keywords)
        if keywords:
            rows = [r for r in rows if r["id"] in hits] or rows
        for r in rows[: MAX_STARS - 1]:
            chosen.append((r, hits.get(r["id"], []), None))
        result.conditions.append(f"{base['title']}와 성별·활동 분야·데뷔 시기가 비슷한 스타")
    elif persons and (not q.structured() or q.inherited):
        for r in persons:
            hits = _keyword_hits(conn, [r["id"]], keywords)
            chosen.append((r, hits.get(r["id"], []), None))
    elif q.structured():
        rows = _candidates(conn, q)
        hits = _keyword_hits(conn, [r["id"] for r in rows], keywords)
        if keywords:
            matched = [r for r in rows if r["id"] in hits]
            missing = [k for k in keywords
                       if not any(k == kw for v in hits.values() for _, _, kw in v)]
            result.missing_keywords = missing
            rows = matched or rows
        for r in rows[:MAX_STARS]:
            chosen.append((r, hits.get(r["id"], []), None))
    elif keywords:
        hits = _bounded_keyword_search(conn, keywords)
        if hits:
            ids = list(hits)[: MAX_STARS * 2]
            rows = conn.execute(select(StarProfile.__table__)
                                .where(StarProfile.id.in_(ids))).mappings().all()
            for r in rows[:MAX_STARS]:
                chosen.append((dict(r), hits.get(r["id"], []), None))
        else:
            result.missing_keywords = keywords

    chosen = chosen[:MAX_STARS]
    need_default = [row["id"] for row, snips, _ in chosen if not snips]
    defaults = _default_snippets(conn, need_default)
    for row, snips, members in chosen:
        result.stars.append(_star(row, snips or defaults.get(row["id"], []), members))
    return result


def search_stars(engine: Engine, message: str, previous: Optional[str] = None,
                 request_id: str = "") -> StarSearchResult:
    """Top stars for a question. Never raises; failures give an empty result."""
    started = time.monotonic()
    try:
        q = parse_query(message)
        if previous and not q.structured():
            q = merge_previous(q, parse_query(previous))
        with engine.connect() as conn:
            if conn.dialect.name == "postgresql":
                conn.execute(text(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}"))
            result = _search(conn, q)
            conn.rollback()
    except Exception as error:  # the chat must work without star data
        logger.error("star_search_failure request_id=%s error_type=%s",
                     request_id, type(error).__name__)
        return StarSearchResult()
    latency_ms = int((time.monotonic() - started) * 1000)
    logger.info("star_search_done request_id=%s hits=%s latency_ms=%s",
                request_id, len(result.stars), latency_ms)
    return result


GENDER_LABEL = {"M": "남", "F": "여"}


REF_OPEN = "<참고자료>"
REF_CLOSE = "</참고자료>"
# '<참고자료>', '</참고자료>' and spaced variants such as '< / 참고 자료 >'
_REF_TAG = re.compile(r"<\s*/?\s*참고\s*자료\s*>")


def _strip_ref_tags(value: str) -> str:
    """Remove the block tags from wiki text so it cannot close the block early."""
    prev = None
    while prev != value:  # '</참고</참고자료>자료>' leaves a tag after one pass
        prev, value = value, _REF_TAG.sub("", value)
    return value


def format_reference(result: StarSearchResult) -> str:
    """The '참고 자료' block for the system prompt ('' when nothing was found).

    Everything between REF_OPEN and REF_CLOSE comes from namuwiki, which anyone can
    edit, so the tags are stripped from the body and SYSTEM_PROMPT tells the model to
    treat the block as data only.
    """
    if not result.stars:
        return ""
    lines = ["참고 자료 (나무위키 문서를 정제·발췌한 것, CC BY-NC-SA 2.0 KR)"]
    for c in result.conditions:
        lines.append("검색 기준: " + c)
    if result.missing_keywords:
        lines.append("자료에서 찾지 못한 조건: " + ", ".join(result.missing_keywords))
    for i, s in enumerate(result.stars, 1):
        facts = []
        if s["kind"] == "group":
            facts.append("그룹")
        if s.get("group_name"):
            facts.append("소속 그룹 " + s["group_name"])
        if s.get("gender") in GENDER_LABEL:
            facts.append("성별 " + GENDER_LABEL[s["gender"]])
        if s.get("birth_year"):
            facts.append(f"{s['birth_year']}년생")
        if s.get("debut_year"):
            facts.append(f"{s['debut_year']}년 데뷔")
        if s.get("birthplace"):
            facts.append("출생지 " + s["birthplace"])
        if s.get("agency"):
            facts.append("소속사 " + s["agency"])
        if s.get("height_cm"):
            facts.append(f"키 {s['height_cm']:g}cm")
        lines.append(f"{i}. {s['title']} ({', '.join(facts) or '프로필 정보 없음'})")
        if s.get("members"):
            lines.append("   멤버: " + ", ".join(s["members"]))
        for snip in s["snippets"]:
            lines.append(f"   [{snip['section']}] {snip['text']}")
        lines.append("   출처: " + s["source_url"])
    body = _strip_ref_tags("\n".join(lines))
    return REF_OPEN + "\n" + body + "\n" + REF_CLOSE


SOURCE_PREFIX = "출처:"


def strip_trailing_source(text: str) -> str:
    """Drop a trailing '출처: ...' line (and the blank lines before it) from an answer."""
    lines = text.rstrip().split("\n")
    if lines and lines[-1].lstrip().startswith(SOURCE_PREFIX):
        lines.pop()
        return "\n".join(lines).rstrip()
    return text


def source_line(result: StarSearchResult) -> str:
    """Attribution appended to the answer by the server ('' when nothing was used)."""
    if not result.stars:
        return ""
    return "출처: 나무위키(CC BY-NC-SA 2.0 KR) - " + ", ".join(result.names)
