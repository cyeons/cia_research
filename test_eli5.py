"""네트워크/API 키 없이 도는 검증. python test_eli5.py"""
import subprocess, tempfile, types
from pathlib import Path

import eli5


def _exits(fn):
    try:
        fn()
    except SystemExit as e:
        return str(e)
    raise AssertionError("SystemExit가 안 났다")


def test_slug():
    assert eli5.slug("https://doi.org/10.1371/journal.pone.0345347") == "journal.pone.0345347"
    assert eli5.slug("C:/p/Wing 2006 (final).pdf") == "Wing_2006__final_"
    assert eli5.slug("https://example.com/") == "example.com"
    # 퍼센트 인코딩된 한글 주소가 읽을 수 있는 파일명이 되어야 한다
    assert eli5.slug("https://ko.wikipedia.org/wiki/%EC%83%81%EB%8C%80%EC%84%B1%EC%9D%B4%EB%A1%A0") == "상대성이론"


def test_url_uses_webfetch():
    assert "WebFetch" in eli5.source_instruction("https://doi.org/10.1/x")


class _FakePage:
    def __init__(self, text): self._text = text
    def get_text(self): return self._text


def _stub_fitz(pages_text):
    eli5.fitz = type("F", (), {"open": staticmethod(lambda path: [_FakePage(t) for t in pages_text])})


def test_pdf_text_extracted_directly_not_delegated_to_read():
    """회귀: Claude Code의 Read 도구는 PDF 렌더링에 pdftoppm(poppler)이 필요한데
    관리자 권한 없는 환경엔 없을 수 있다. 대체 경로인 pdftotext도(이 PC에 흔한
    2017년 xpdf 4.00) 한글 CID 매핑을 못 읽어 한글이 통째로 사라진다(실측:
    96,447자 추출 중 한글 0자). PyMuPDF로 우리가 직접 뽑아 프롬프트에 통째로 넣는다."""
    _stub_fitz(["초등학교 정보교육 실험 결과 " * 20, " 두 번째 페이지 내용 " * 20])
    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "a.pdf"); p.write_bytes(b"%PDF-1.4 fake")
        ins = eli5.source_instruction(str(p))
    assert "초등학교 정보교육 실험 결과" in ins and "두 번째 페이지 내용" in ins
    assert "Read 도구" not in ins and "pages 인자" not in ins   # Read에 위임하지 않는다


def test_pdf_extraction_guards_near_empty_scans():
    """스캔본이라 텍스트 층이 없으면 몇 글자만 나온다 - 그걸로 요약하면 지어내는 것과 같다."""
    _stub_fitz(["x"])
    assert "텍스트가 거의 안" in _exits(lambda: eli5.extract_pdf_text("dummy.pdf"))


def test_pdf_extraction_without_pymupdf_fails_loudly():
    eli5.fitz = None
    assert "pymupdf가 설치돼 있지 않습니다" in _exits(lambda: eli5.extract_pdf_text("dummy.pdf"))


def test_bad_inputs_fail_loudly():
    with tempfile.TemporaryDirectory() as d:
        assert "파일이 없습니다" in _exits(lambda: eli5.source_instruction(str(Path(d, "no.pdf"))))
        txt = Path(d, "a.txt"); txt.write_text("x")
        assert "PDF가 아닙니다" in _exits(lambda: eli5.source_instruction(str(txt)))


def _stub_run(rc=0, stdout="<h2>요약</h2>", stderr="", seen=None):
    eli5.shutil = types.SimpleNamespace(which=lambda n: "C:/fake/claude.cmd")
    def run(cmd, **kw):
        if seen is not None:
            seen.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, rc, stdout, stderr)
    eli5.subprocess = types.SimpleNamespace(run=run, CompletedProcess=subprocess.CompletedProcess)


def test_invocation_is_headless_and_utf8():
    seen = []
    _stub_run(stdout="```html\n<h2>요약</h2>\n```", seen=seen)
    assert eli5.run_claude("q") == "<h2>요약</h2>"      # 코드펜스 제거
    cmd, kw = seen[0]
    assert "-p" in cmd and "--allowed-tools" in cmd
    tools = cmd[cmd.index("--allowed-tools") + 1]
    assert "Skill" in tools          # 없으면 artifact-design을 부를 수단이 없다
    assert "Write" not in tools and "Bash" not in tools      # 쓰기·실행 도구는 안 준다
    assert "--max-turns" in cmd                        # 긴 PDF도 끝까지, 단 무한은 아니게
    # 한국어 윈도우 기본 인코딩(cp949)으로 읽으면 한글이 깨진다.
    assert kw["encoding"] == "utf-8"


def test_missing_cli_and_failures_exit():
    eli5.shutil = types.SimpleNamespace(which=lambda n: None)
    assert "찾을 수 없습니다" in _exits(lambda: eli5.run_claude("q"))
    _stub_run(rc=1, stderr="boom")
    assert "boom" in _exits(lambda: eli5.run_claude("q"))
    _stub_run(rc=0, stdout="   ", stderr="why")
    assert "비었습니다" in _exits(lambda: eli5.run_claude("q"))


def test_prompt_goes_through_stdin_not_argv():
    """회귀: 멀티라인 프롬프트를 argv로 주면 claude.CMD가 첫 줄에서 잘라버린다.

    조용히 잘리기 때문에(에러 없음) 지시 대부분이 사라진 채 실행되고,
    엉뚱한 응답이 나온다. 실제로 한 번 당했다.
    """
    seen = []
    _stub_run(seen=seen)
    multi = "첫 줄\n둘째 줄 <h2>꺾쇠</h2>\n셋째 줄"
    eli5.run_claude(multi)
    cmd, kw = seen[0]
    assert kw["input"] == multi                                  # stdin으로 온전히
    assert not any("둘째 줄" in c for c in cmd)                   # argv엔 흔적도 없어야
    assert cmd[cmd.index("-p") + 1].startswith("--")             # -p 뒤에 프롬프트를 붙이지 않는다


def test_prompt_actually_contains_every_block():
    """회귀: DIAGRAMS가 프롬프트 조립에서 빠진 채로 두 번 돌았다.

    파일에 상수가 있는지 확인하는 것으로는 못 잡는다. 조립 결과를 봐야 한다.
    """
    p = eli5.build_prompt("https://doi.org/10.1/x")
    for name, block in [("DESIGN", eli5.DESIGN), ("RULES", eli5.RULES),
                        ("DIAGRAMS", eli5.DIAGRAMS), ("SECTIONS", eli5.SECTIONS)]:
        assert block in p, f"{name}가 프롬프트에서 빠졌다"
    assert "https://doi.org/10.1/x" in p                  # 읽을 대상
    assert "반드시 <svg>" in p                             # 문자 도형 금지 조항
    assert "최소 3개" in p                                 # 그림 개수 하한
    assert "artifact-design" in p                          # 디자인 스킬 로드 지시


def test_split_title():
    t, frag = eli5.split_title("<!--TITLE: 로봇으로 배운 아이들-->\n<h2>x</h2>", "대체")
    assert t == "로봇으로 배운 아이들" and frag.strip() == "<h2>x</h2>"
    assert eli5.split_title("<h2>x</h2>", "대체") == ("대체", "<h2>x</h2>")


def test_sections_bail_out_on_compilation_documents():
    """회귀: 섹션 틀이 '단일 연구 논문'만 전제하면, 동향 리포트를 넣었을 때 끝에 실린
    논문 한두 편만 정리하고 본문을 통째로 빠뜨린다(KERIS 40쪽 매거진에서 실제로 그랬다).

    그렇다고 여러 주제용 틀을 따로 두는 것도 답이 아니었다 - 설명할 메커니즘이 하나로
    없는 문서에 그림을 강제하면 설명이 아니라 장식이 된다. 이 도구는 연구 하나만 맡고,
    나머지는 안 맞는다고 말한 뒤 길잡이만 준다.
    """
    p = eli5.build_prompt("https://doi.org/10.1/x")
    assert "여러 주제를 모은 것이면" in p                 # 감지 지시
    assert "아래 섹션 틀을 쓰지 마라" in p                 # 강제로 채우지 않게
    assert "그림을 그리지 말고" in p                       # 장식용 그림 금지
    assert "어디부터 읽을까" in p                          # 대신 주는 것
    # 여러 주제용 본문 섹션을 따로 만들지 않는다
    assert "이 문서가 다루는 지형" not in p and "반복되는 흐름" not in p


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
