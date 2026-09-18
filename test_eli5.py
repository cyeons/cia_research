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


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
