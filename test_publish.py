"""네트워크 없이 도는 검증. python test_publish.py"""
import shutil, tempfile
from pathlib import Path

import publish

PAGE = ('<!doctype html><html><body><h1>교실 속 AI의 윤리 위험 15가지</h1>'
        '<div class="callout">AI를 교실에 들일 때 무엇을 조심해야 하나.</div>'
        '<p>본문</p></body></html>')


def test_meta_reads_title_and_one_liner():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "x.html"); p.write_text(PAGE, encoding="utf-8")
        title, one = publish.meta(p)
    assert title == "교실 속 AI의 윤리 위험 15가지"
    assert one == "AI를 교실에 들일 때 무엇을 조심해야 하나."


def test_index_groups_by_date_newest_first():
    """격주로 쌓이므로 최신 회차가 위에 와야 한다."""
    with tempfile.TemporaryDirectory() as d:
        cwd = Path.cwd()
        import os; os.chdir(d)
        try:
            publish.ROOT = Path("docs/study"); publish.INDEX = publish.ROOT / "index.html"
            for day in ("2026-09-08", "2026-09-22"):
                (publish.ROOT / day).mkdir(parents=True)
                (publish.ROOT / day / "a.html").write_text(PAGE, encoding="utf-8")
            n = publish.build_index()
            idx = publish.INDEX.read_text(encoding="utf-8")
        finally:
            os.chdir(cwd)
    assert n == 2
    assert idx.index("2026-09-22") < idx.index("2026-09-08")   # 최신이 위
    assert "교실 속 AI의 윤리 위험 15가지" in idx
    assert 'href="2026-09-22/a.html"' in idx                   # 상대 경로로 열려야


def test_published_filename_comes_from_title():
    """원본 파일명엔 로컬 경로가 그대로 박혀 있다
    (C__Projects_cia_research_pdf__8월호__...). 공개 URL로 쓸 수 없다."""
    assert publish.name_slug("교실 속 AI의 윤리 위험 15가지").startswith("교실")
    assert "/" not in publish.name_slug("A / B")


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
