"""네트워크 없이 도는 최소 검증. python test_weekly.py"""
import os
os.environ.setdefault("MAIL_TO", "test@example.com")
import types

import weekly

_REAL_OA = weekly.oa          # 다른 테스트가 weekly.oa를 가짜로 덮어쓴다


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


def test_summarize_link_rules_cover_every_section():
    """회귀: 링크 규칙이 links 객체(해외 논문)만 언급하면, doi/url 필드뿐인
    이론적 배경·국내 동향 섹션은 모델이 아예 링크를 안 걸어버린다.
    지난 브리핑에서 국내 동향이 0건이라 못 드러났을 뿐, 데이터가 들어오면 터진다."""
    calls = []
    weekly.gemini = lambda system, prompt: calls.append((system, prompt)) or "<h2>x</h2>"
    weekly.summarize([], [], [], [], [], None)
    system, prompt = calls[0]
    assert "doi 필드" in system and "url 필드" in system      # 링크 형태 전부 명시
    assert "doi로 링크" in prompt                              # 이론적 배경 섹션 지시
    assert "url 필드로 링크" in prompt                         # 국내 동향 섹션 지시
    assert "KERIS" in system                                   # KERIS도 링크 규칙 안에


def test_keris_parses_issue_and_pdf_link():
    """KERIS는 공개 API가 없어 HTML을 긁는다. 3단계 체인이 다 이어져야 PDF에 닿는다:
    POST 목록 -> data-id(fileGrpKey) -> fileDownChk.do JSON -> fileDownload.do"""
    row = ("<tr><td>번호 363</td>"
           "<td>[통권 224호] 2026 KERIS 디지털교육 글로벌 동향 리포트</td>"
           "<td>담당자 곽병일</td><td>발행년도 2026</td>"
           '<td><a class="listFileDown" data-id="19764">첨부</a></td></tr>')
    html = "<table><tr><th>번호</th></tr>" + row + "</table>"

    def fake_urlopen(req, timeout=None):
        import io as _io, json as _json
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if "fileDownChk" in url:
            body = _json.dumps({"infoMediaFileList": [
                {"fileKey": "abc123", "orignlFileNm": "(8월호) 리포트_224호.pdf",
                 "fileSize": 41672211}]}).encode()
        else:
            body = html.encode("utf-8")
        class R:
            def __enter__(self): return _io.BytesIO(body)
            def __exit__(self, *a): return False
        return R()
    weekly.urllib.request.urlopen = fake_urlopen

    r = weekly.keris_latest()
    assert r["issue"] == 224, r
    assert "fileKey=abc123" in r["url"] and "dwlTy=pblcte" in r["url"]
    assert r["mb"] == 39.7                       # 41,672,211 바이트
    assert "통권 224호" in r["title"]


def test_keris_broken_html_does_not_kill_the_brief():
    """HTML 구조가 바뀌어도 브리핑 전체는 나가야 한다 - 이 섹션만 빈다."""
    def fake_urlopen(req, timeout=None):
        import io as _io
        class R:
            def __enter__(self): return _io.BytesIO("<html>개편했습니다</html>".encode("utf-8"))
            def __exit__(self, *a): return False
        return R()
    weekly.urllib.request.urlopen = fake_urlopen
    assert weekly.keris_latest() is None          # 예외가 아니라 None


def test_reviews_filters_to_review_type():
    """1차 연구만 모으면 지엽적이 된다. type:review 가 빠지면 이 섹션의 존재 이유가 없다."""
    seen = {}
    def fake_oa(**params):
        seen.update(params)
        return {"results": [{"title": "A Systematic Literature Review of AI Literacy",
                             "publication_year": 2026, "cited_by_count": 147,
                             "abstract_inverted_index": {"We": [0], "reviewed": [1]},
                             "primary_location": {"source": {"display_name": "Computers & Education"}},
                             "open_access": {"is_oa": True},
                             "best_oa_location": {"pdf_url": "https://x.example/r.pdf"},
                             "doi": "https://doi.org/10.1/r"}]}
    weekly.oa = fake_oa

    out = weekly.reviews()
    assert "type:review" in seen["filter"]
    assert out[0]["links"]["pdf"] == "https://x.example/r.pdf"   # eli5.py에 바로 넣을 수 있게
    assert out[0]["abstract"] == "We reviewed"


def test_openalex_retries_on_429():
    """회귀: 한 번 돌 때 OpenAlex를 7번 부른다. Actions 러너는 IP를 공유해서
    polite pool에 있어도 429가 난다. 리뷰 호출 하나 때문에 브리핑 전체가 죽었다."""
    import urllib.error, io as _io, json as _json
    calls = {"n": 0}
    def flaky(url, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        class R:
            def __enter__(self): return _io.BytesIO(_json.dumps({"results": []}).encode())
            def __exit__(self, *a): return False
        return R()
    weekly.urllib.request.urlopen = flaky
    weekly.time = types.SimpleNamespace(sleep=lambda s: None)   # 테스트에서 35초 기다리지 않는다
    weekly.oa = _REAL_OA

    assert weekly.oa(filter="x") == {"results": []}
    assert calls["n"] == 3                       # 두 번 실패하고 세 번째에 성공


def test_reviews_failure_does_not_kill_the_brief():
    def boom(**kw): raise RuntimeError("OpenAlex 다운")
    weekly.oa = boom
    assert weekly.reviews() == []                # 예외가 아니라 빈 목록


def test_search_covers_the_teacher_relevance_criteria():
    """정확성 기준: 초등 교사가 자기 교실과 연결지을 수 있는 것.
    주제가 세 갈래(AI/디지털 수업, AI 윤리, 디지털 과몰입)로 넓어졌고,
    교실 맥락(CONTEXT)이 필수다 - 이게 빠지면 같은 '과몰입' 검색이
    비만·충치·자세 같은 보건 연구를 상위로 올린다(실측)."""
    for kw in ("AI ethics", "digital citizenship", "screen time", "smartphone addiction"):
        assert kw in weekly.TOPIC, f"{kw}가 주제에서 빠졌다"
    assert "classroom" in weekly.CONTEXT and "teacher" in weekly.CONTEXT
    for kw in ("obesity", "dental", "higher education", "undergraduate"):
        assert kw in weekly.EXCLUDE, f"{kw}를 배제하지 않는다"
    assert all(part in weekly.SEARCH for part in (weekly.TOPIC, weekly.LEVEL,
                                                  weekly.CONTEXT, weekly.EXCLUDE))


def test_papers_sorted_by_relevance_and_skips_already_sent(tmp="_p"):
    """최신성이 아니라 정확성 우선. 그러면 매주 같은 상위 논문이 반복되므로
    한 번 보낸 것은 건너뛴다."""
    import os, shutil, json as _json
    os.makedirs(tmp, exist_ok=True); cwd = os.getcwd(); os.chdir(tmp)
    try:
        os.makedirs("docs", exist_ok=True)
        with open(weekly.SEEN_PAPERS_PATH, "w", encoding="utf-8") as f:
            _json.dump({"ids": ["W_old"]}, f)
        seen_params = {}
        def fake_oa(**params):
            seen_params.update(params)
            return {"results": [
                {"id": "W_old", "title": "이미 보낸 것", "referenced_works": []},
                {"id": "W_new", "title": "새로 고른 것", "referenced_works": []}]}
        weekly.oa = fake_oa

        out = weekly.papers(n=5)
        assert "relevance_score:desc" in seen_params["sort"]     # 최신순이 아니라 정확도순
        assert [w["id"] for w in out] == ["W_new"]               # 이미 보낸 것은 제외
        after = _json.load(open(weekly.SEEN_PAPERS_PATH, encoding="utf-8"))["ids"]
        assert "W_new" in after and "W_old" in after             # 이번 것도 기억에 추가
    finally:
        os.chdir(cwd); shutil.rmtree(tmp)


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
