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
    # 단일 논문 페이지에 "주간 브리핑" 제목이 붙으면 안 된다
    solo = weekly.render("<p>x</p>", title="상대성이론 읽기")
    assert "<h1>상대성이론 읽기</h1>" in solo and "주간 브리핑" not in solo


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


def test_domestic_uses_crossref_no_key_needed():
    """KCI는 신청 IP(고정 서버 IP)를 요구해 GitHub Actions와 안 맞는다.
    Crossref는 키도 IP도 없다 — 그게 이 함수가 존재하는 이유다."""
    seen = {}
    def fake_urlopen(url, timeout=None):
        seen["url"] = url
        import io as _io, json as _json
        body = _json.dumps({"message": {"items": [
            {"title": ["Elementary AI Ethics"], "original-title": ["초등 AI 윤리"],
             "DOI": "10.14352/x.1", "published": {"date-parts": [[2026]]}}]}}).encode()
        class R:
            def __enter__(self): return _io.BytesIO(body)
            def __exit__(self, *a): return False
        return R()
    weekly.urllib.request.urlopen = fake_urlopen

    out = weekly.domestic(n=5)
    assert "api.crossref.org" in seen["url"]
    assert "key" not in seen["url"].lower()             # 인증키 없음
    assert out[0]["title"] == "초등 AI 윤리"              # 원제(한글) 우선
    assert out[0]["url"] == "https://doi.org/10.14352/x.1"


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
