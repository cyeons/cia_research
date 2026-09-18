"""네트워크 없이 도는 최소 검증. python test_weekly.py"""
import os
os.environ.setdefault("MAIL_TO", "test@example.com")
import weekly


def test_unabstract():
    inv = {"Computational": [0], "thinking": [1, 4], "in": [2], "primary": [3]}
    assert weekly.unabstract(inv) == "Computational thinking in primary thinking"
    assert weekly.unabstract(None) == ""


def test_foundations_counts_shared_refs_only():
    papers = [
        {"referenced_works": ["https://openalex.org/W1", "https://openalex.org/W2"]},
        {"referenced_works": ["https://openalex.org/W1", "https://openalex.org/W3"]},
        {"referenced_works": ["https://openalex.org/W1"]},
        {"referenced_works": None},
    ]
    seen = {}
    weekly.oa = lambda **kw: (seen.update(kw), {"results": [
        {"id": "https://openalex.org/W1", "title": "Wing 2006", "publication_year": 2006}]})[1]

    got = weekly.foundations(papers)
    # W1은 3편이 공통 인용 -> 채택. W2/W3은 1편뿐 -> 탈락(이론적 배경이 아니라 그냥 참고문헌).
    assert [g["co_cited_by"] for g in got] == [3], got
    assert seen["filter"] == "openalex_id:W1", seen["filter"]


def test_foundations_empty():
    assert weekly.foundations([{"referenced_works": ["https://openalex.org/W9"]}]) == []


def test_render_is_standalone_and_utf8_safe():
    doc = weekly.render("<h2>이번 주 흐름</h2>", "https://x.example/2026-01-01.html")
    assert doc.startswith("<!doctype html>") and 'charset="utf-8"' in doc
    assert "이번 주 흐름" in doc and "@page" in doc          # 브라우저 PDF 저장용
    assert "prefers-color-scheme" in doc                   # 어두운 배경에서도 읽히게
    assert "var(--" not in doc                             # Gmail이 CSS 변수를 제거한다
    assert "https://x.example/2026-01-01.html" in doc
    assert "href" not in weekly.render("<p>x</p>")            # 링크 없으면 배너도 없음


def test_archive_writes_page_and_rebuilds_index(tmp="_t"):
    import os, shutil
    os.makedirs(tmp, exist_ok=True); cwd = os.getcwd(); os.chdir(tmp)
    try:
        os.makedirs("docs", exist_ok=True)
        open("docs/2020-01-01.html", "w").close()             # 과거 주차
        weekly.archive(weekly.render("<p>본문</p>"))
        idx = open("docs/index.html", encoding="utf-8").read()
        today = f"{weekly.date.today()}.html"
        assert today in idx and "2020-01-01.html" in idx
        assert idx.index(today) < idx.index("2020-01-01")     # 최신이 위
        assert "본문" in open(f"docs/{today}", encoding="utf-8").read()
    finally:
        os.chdir(cwd); shutil.rmtree(tmp)


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
