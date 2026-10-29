from scripts.namuwiki.chunk import chunk, sections


def para(n, word="가나다라마바사아자차"):
    return (word * (n // len(word) + 1))[:n]


def test_sections_keep_heading_path():
    text = "== 개요 ==\n소개\n== 활동 ==\n=== 2020년 ===\n데뷔\n== 여담 ==\n끝"
    assert sections(text) == [("개요", "소개"), ("활동 > 2020년", "데뷔"), ("여담", "끝")]


def test_text_before_heading_is_overview():
    assert sections("머리말\n== 활동 ==\n본문") == [("개요", "머리말"), ("활동", "본문")]


def test_chunks_are_at_most_max_chars():
    body = "\n\n".join(para(n) for n in (300, 450, 900, 1500, 120, 2600))
    text = f"== 활동 ==\n{body}\n== 여담 ==\n{para(80)}"

    chunks = chunk(text)

    assert chunks
    assert all(len(c) <= 1000 for _, c in chunks)
    assert all(len(c) >= 400 for _, c in chunks[:-1])
    joined = "".join(c for _, c in chunks)
    assert len(joined.replace("\n", "").replace(" ", "")) >= 300 + 450 + 900 + 1500 + 120 + 2600


def test_long_sentences_split_at_sentence_end():
    sentence = para(300) + "다. "
    chunks = chunk("== 활동 ==\n" + sentence * 8)
    assert len(chunks) >= 2
    assert all(len(c) <= 1000 for _, c in chunks)
    assert chunks[0][1].endswith("다.")


def test_short_sections_are_merged_with_title_inline():
    chunks = chunk("== 학력 ==\n서울초등학교\n== 가족 ==\n부모님\n== 여담 ==\n" + para(990))
    assert chunks[0][0] == "학력 | 가족"
    assert chunks[0][1] == "서울초등학교\n\n[가족]\n부모님"
    assert chunks[1][0] == "여담"


def test_navigation_sections_are_skipped():
    chunks = chunk("== 개요 ==\n" + para(600) + "\n== 둘러보기 ==\n다른 그룹 목록")
    assert [s for s, _ in chunks] == ["개요"]
