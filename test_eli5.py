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


def test_url_uses_webfetch_pdf_uses_read():
    assert "WebFetch" in eli5.source_instruction("https://doi.org/10.1/x")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "a.pdf"); p.write_bytes(b"%PDF-1.4 fake")
        ins = eli5.source_instruction(str(p))
    assert "Read" in ins and "pages" in ins      # 긴 PDF를 잘라 읽으라는 지시가 살아있어야 한다
    assert str(Path(p).resolve()) in ins         # 상대경로면 claude가 못 찾는다


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
    assert cmd[cmd.index("--allowed-tools") + 1] == "Read,WebFetch"   # 쓰기 도구는 안 준다
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
    for name, block in [("RULES", eli5.RULES), ("DIAGRAMS", eli5.DIAGRAMS),
                        ("SECTIONS", eli5.SECTIONS)]:
        assert block in p, f"{name}가 프롬프트에서 빠졌다"
    assert "https://doi.org/10.1/x" in p                  # 읽을 대상
    assert "반드시 <svg>" in p                             # 문자 도형 금지 조항
    assert "최소 3개" in p                                 # 그림 개수 하한


def test_split_title():
    t, frag = eli5.split_title("<!--TITLE: 로봇으로 배운 아이들-->\n<h2>x</h2>", "대체")
    assert t == "로봇으로 배운 아이들" and frag.strip() == "<h2>x</h2>"
    assert eli5.split_title("<h2>x</h2>", "대체") == ("대체", "<h2>x</h2>")


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
