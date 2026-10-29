"""Category rules that decide which documents are Korean stars (persons) or groups.

Signals a person document can have:
  S1  Korean entertainer job category (한국 여가수, 대한민국의 영화배우 ...)
  S2  idol role category (아이돌 보컬 ...). Not country specific.
  S3  category named after a group document, or '<group>/멤버'
  S4  '<agency> 소속 아티스트' where <agency> is a Korean entertainment agency
  S5  '인터넷 밈/가수/대한민국' etc. Only used as Korean evidence.
  S6  entertainment awards / '... 출신 방송인' (예능 stars)
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping

S1 = {
    "한국 남가수", "한국 여가수", "한국 가수", "대한민국의 가수", "대한민국의 남성 가수",
    "한국 남배우", "한국 여배우", "대한민국의 배우", "대한민국의 드라마 배우",
    "대한민국의 영화배우",
    "대한민국의 뮤지컬 배우", "대한민국의 연극배우",
    "한국의 남성 래퍼", "한국의 여성 래퍼", "한국 래퍼", "대한민국의 래퍼",
    "한국 여성 모델", "한국 남성 모델", "대한민국의 모델", "대한민국의 패션 모델",
    "대한민국의 남성 방송인", "대한민국의 여성 방송인", "대한민국의 방송인",
    "한국 남성 코미디언", "한국 여성 코미디언",
    "대한민국의 싱어송라이터", "대한민국의 R&B 가수", "대한민국의 멀티 엔터테이너",
    "대한민국의 보컬리스트",
    "한국 아이돌", "해외에서 활동하는 한국인 아이돌", "트로트 가수", "대한민국의 연예인",
    "대한민국의 남성 댄서", "대한민국의 여성 댄서", "대한민국의 댄서",
}
# S1 categories that also hold non-entertainers (announcers, ex-athletes, racing models ...)
S1_WEAK = {
    "대한민국의 남성 방송인", "대한민국의 여성 방송인", "대한민국의 방송인",
    "한국 여성 모델", "한국 남성 모델", "대한민국의 모델", "대한민국의 패션 모델",
    "대한민국의 연예인", "대한민국의 남성 댄서", "대한민국의 여성 댄서", "대한민국의 댄서",
}
S2 = {"아이돌 보컬", "아이돌 댄서", "아이돌 래퍼", "아이돌 리더", "아이돌 센터"}
S5 = {
    "인터넷 밈/가수/대한민국", "인터넷 밈/배우/대한민국",
    "인터넷 밈/래퍼/대한민국", "인터넷 밈/예능인/대한민국",
}
GROUP_CATEGORIES = {
    "대한민국의 걸그룹", "대한민국의 보이그룹", "대한민국의 혼성그룹", "대한민국의 힙합 그룹",
    "대한민국의 보이밴드그룹",
}
AGENCY_CATEGORIES = {"대한민국의 연예 기획사", "대한민국의 없어진 연예 기획사"}

BIRTH_RE = re.compile(r"^\d{3,4}년 출생$")
DEBUT_RE = re.compile(r"^\d{4}년 데뷔$")
CLAN_RE = re.compile(r"^[가-힣]{1,4} [가-힣]{1,2}씨( .+파)?$")  # 본관, e.g. '평택 임씨'
AGENCY_MEMBER_RE = re.compile(r"^(.+?) 소속 (아티스트|연예인|배우|가수)$")
FOREIGN_JOB_RE = re.compile(
    r"^(일본|중국|미국|영국|대만|태국|캐나다|프랑스|독일|호주|홍콩|필리핀|베트남|인도네시아|러시아)"
    r"(의)? ?"
    r"(남|여)?(성 )?(가수|배우|아이돌|래퍼|모델|싱어송라이터|성우)"
)
# albums, programs, crews ... that still carry person categories (checked only without a birth year)
NON_PERSON_RE = re.compile(
    r"(방송 프로그램|음반|노래|싱글|OST|팬덤|콘서트|투어|인조 음악 그룹|결성된 음악 그룹|댄스 크루|"
    r"드라마 장르|영화제|행사)$"
)
S6_RE = re.compile(r"^(KBS|MBC|SBS) 연예대상 수상자$|출신 방송인$|^백상예술대상 .*수상자$")
# entertainment evidence that keeps a weak-S1 document despite another profession
ENTERTAINMENT_RE = re.compile(
    r"연예대상|출신 방송인|고정 출연진|/출연진$|역대 진행자|역대 MC|역대 DJ|의 멤버$|예능인"
)
PROFESSION_RE = re.compile(
    r"야구|축구|농구|배구|골프|테니스|격투기|복싱|씨름|빙상|쇼트트랙|피겨|유도|태권도|레슬링|육상|수영|"
    r"e스포츠|프로게이머|정치인|기업인|아나운서|기자|언론인|교수|의사|변호사|요리사|셰프|"
    r"선수$|감독$|해설위원|캐스터"
)


def strip_paren(title: str) -> str:
    """'안테나(기업)' -> '안테나' (agency categories use the bare name)."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", title)


def find_groups(docs: Mapping[str, set[str]]) -> set[str]:
    return {t for t, cats in docs.items() if cats & GROUP_CATEGORIES}


def find_agencies(docs: Mapping[str, set[str]]) -> set[str]:
    agencies = {t for t, cats in docs.items() if cats & AGENCY_CATEGORIES}
    return agencies | {strip_paren(t) for t in agencies}


def person_signals(cats: set[str], groups: set[str], agencies: set[str]) -> list[str]:
    sig = []
    if cats & S1:
        sig.append("S1")
    if cats & S2:
        sig.append("S2")
    if any((c[: -len("/멤버")] if c.endswith("/멤버") else c) in groups for c in cats):
        sig.append("S3")
    for c in cats:
        m = AGENCY_MEMBER_RE.match(c)
        if m and m.group(1) in agencies:
            sig.append("S4")
            break
    if cats & S5:
        sig.append("S5")
    if any(S6_RE.search(c) for c in cats):
        sig.append("S6")
    return sig


def judge_person(cats: set[str], sig: list[str]) -> str | None:
    """None if the document is kept as a person, otherwise the reason it is dropped."""
    if not sig:
        return "no_signal"
    if sig == ["S5"]:
        return "drop_S5_only"
    has_debut = any(DEBUT_RE.match(c) for c in cats)
    if set(sig) <= {"S4", "S5"} and not has_debut:
        return "drop_S4_without_debut"

    has_birth = any(BIRTH_RE.match(c) for c in cats)
    has_clan = any(CLAN_RE.match(c) for c in cats)
    s1 = cats & S1
    is_person = has_birth or has_clan or bool(s1) or bool(cats & S2)
    korean = bool(s1) or bool(set(sig) & {"S3", "S4", "S5", "S6"}) or has_clan
    foreign_only = (
        not s1
        and any(FOREIGN_JOB_RE.match(c) for c in cats)
        and "S3" not in sig
        and "S5" not in sig
    )
    if not has_birth and any(NON_PERSON_RE.search(c) for c in cats):
        is_person = False
    weak_only = not (cats & (S1 - S1_WEAK)) and not (set(sig) & {"S2", "S3"})
    if (
        weak_only
        and any(PROFESSION_RE.search(c) for c in cats)
        and not any(ENTERTAINMENT_RE.search(c) for c in cats)
    ):
        return "drop_weak_s1_with_other_profession"
    if not is_person:
        return "drop_not_person"
    if not korean:
        return "drop_no_korean_signal"
    if foreign_only:
        return "drop_foreign_only"
    return None


class Selection:
    def __init__(self) -> None:
        self.groups: set[str] = set()
        self.persons: dict[str, list[str]] = {}  # title -> signals
        self.stats: Counter = Counter()

    def kind_of(self, title: str) -> str | None:
        if title in self.persons:
            return "person"
        if title in self.groups:
            return "group"
        return None


def select(
    docs: Mapping[str, set[str]], known_groups: Iterable[str] = ()
) -> Selection:
    """Pick groups and persons among root documents.

    docs: title -> effective categories, for non-redirect documents without '/' in the title.
    known_groups: extra group titles for S3 only (e.g. when the group page is not in the input).
    """
    sel = Selection()
    sel.groups = find_groups(docs)
    s3_groups = sel.groups | set(known_groups)
    agencies = find_agencies(docs)
    for title, cats in docs.items():
        if title in sel.groups:
            continue
        sig = person_signals(cats, s3_groups, agencies)
        reason = judge_person(cats, sig)
        if reason is None:
            sel.persons[title] = sig
            sel.stats["persons_sig_" + "+".join(sig)] += 1
        elif reason != "no_signal":
            sel.stats[reason] += 1
    sel.stats["groups"] = len(sel.groups)
    sel.stats["persons"] = len(sel.persons)
    return sel
