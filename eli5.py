"""논문 하나를 ELI5 HTML로 만들어 브라우저에 띄운다.

    python eli5.py paper.pdf
    python eli5.py https://doi.org/10.1371/journal.pone.0345347

로컬 Claude Code(`claude -p`)를 헤드리스로 부른다. 구독으로 처리되므로 API 키가 필요 없다.
PDF는 Claude Code의 Read가, 웹 주소는 WebFetch가 읽는다 — 파싱 라이브러리도 필요 없다.
"""
import os, re, shutil, subprocess, sys, urllib.parse, webbrowser
from pathlib import Path

from weekly import render          # 메일 브리핑과 같은 인쇄용 스타일을 그대로 쓴다

MODEL = "opus"
MAX_TURNS = "30"                   # 긴 PDF는 Read를 20쪽씩 여러 번 부른다

RULES = """너는 초등 컴퓨터교육·AI교육을 공부하는 대학원생의 논문 읽기 도우미다.
원문에 없는 내용을 지어내지 마라. 원문에서 확인이 안 되는 항목은 '논문에 명시 없음'이라고 써라.
숫자(표본 수, 효과크기, p값 등)는 원문 그대로 인용하되, 쉬운 설명 쪽에서는 '차이가 꽤 컸다' 같은 일상어로 풀어라.

출력은 HTML 조각(<h2>/<p>/<ul>/<table>)만 내라. 설명이나 인사말을 앞뒤에 붙이지 마라.
<html>/<body> 태그와 마크다운 코드펜스(```)도 쓰지 마라."""

SECTIONS = """논문을 다 읽은 뒤 아래 순서 그대로 정리해라. 한국어.

<h2>한 문단 요약</h2>
초등학교 6학년이 읽어도 이해되는 5~6문장. 전문용어 0개. 필요하면 일상 비유를 써라.

<h2>무엇이 궁금했나</h2>
저자가 풀려던 문제와 그게 왜 문제인지. 쉬운 말로.

<h2>어떻게 알아봤나</h2>
연구 방법을 이야기처럼. "누구 몇 명에게 / 얼마 동안 / 무엇을 시켰고 / 무엇을 쟀다". 도구나 검사지 이름은 괄호로 병기.

<h2>무엇을 알아냈나</h2>
핵심 결과 3~5개를 <ul>로. 각 항목은 쉬운 말 한 문장 + 괄호 안에 원문 수치.

<h2>초등 현장에 주는 시사점</h2>
수업에 실제로 옮길 수 있는 것과, 이 논문만으로는 아직 말할 수 없는 것을 나눠서.

<h2>한계와 조심할 점</h2>
표본·설계·일반화의 한계. 저자가 밝힌 것과 네가 보기에 걸리는 것을 구분해서 써라.

<h2>연구적 위치</h2>
여기서는 학술 용어를 써도 된다. 어떤 이론적 틀에 서 있는지, 어떤 선행연구를 딛고 있는지.
논문이 반복해서 인용하는 핵심 문헌을 <ul>로 3~6개, 각각 이 논문에서 어떤 역할인지 한 줄씩."""


def source_instruction(src):
    """원문을 어떻게 읽을지 지시하는 한 줄."""
    if src.startswith(("http://", "https://")):
        return f"WebFetch로 다음 주소의 논문을 가져와 전문을 읽어라: {src}"
    path = Path(src)
    if not path.is_file():
        sys.exit(f"파일이 없습니다: {src}")
    if path.suffix.lower() != ".pdf":
        sys.exit(f"PDF가 아닙니다: {src} (PDF 파일이나 http(s) 주소를 주세요)")
    return (f"Read 도구로 다음 PDF를 읽어라: {path.resolve()}\n"
            f"10쪽이 넘으면 pages 인자로 20쪽씩 나눠 끝까지 읽어라. 일부만 읽고 요약하지 마라.")


def run_claude(prompt):
    exe = shutil.which("claude")
    if not exe:
        sys.exit("`claude` 명령을 찾을 수 없습니다. Claude Code가 설치되고 PATH에 있어야 합니다.")
    # 프롬프트는 반드시 stdin으로. 윈도우의 claude.CMD 셔임을 거치면 argv로 준
    # 멀티라인 문자열이 첫 줄에서 잘린다(조용히, 에러 없이). 그러면 지시 대부분이
    # 사라진 채로 실행돼 엉뚱한 응답이 나온다.
    r = subprocess.run(
        [exe, "-p", "--output-format", "text", "--model", MODEL,
         "--max-turns", MAX_TURNS, "--allowed-tools", "Read,WebFetch"],
        input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        sys.exit(f"claude 실행 실패 (exit {r.returncode}):\n{(r.stderr or r.stdout)[:1500]}")
    out = re.sub(r"^\s*```(?:html)?\s*|\s*```\s*$", "", r.stdout).strip()
    if not out:
        sys.exit(f"응답이 비었습니다:\n{r.stderr[:800]}")
    return out


def slug(src):
    # 한글 주소는 퍼센트 인코딩돼 있다. 풀지 않으면 파일명이 _EC_83_81... 이 된다.
    base = urllib.parse.unquote(src).rstrip("/").rsplit("/", 1)[-1].removesuffix(".pdf") or "paper"
    return re.sub(r"[^\w.-]", "_", base, flags=re.UNICODE)[:60]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    prompt = f"{RULES}\n\n{source_instruction(src)}\n\n{SECTIONS}"
    print(f"읽는 중: {src}", file=sys.stderr)

    fragment = run_claude(prompt)
    origin = src if src.startswith("http") else Path(src).resolve().as_uri()
    doc = render(f'<p style="font-size:.9em">원문: <a href="{origin}">{src}</a></p>{fragment}')

    os.makedirs("eli5", exist_ok=True)
    out = Path("eli5") / f"{slug(src)}.html"
    out.write_text(doc, encoding="utf-8")
    print(f"저장: {out}", file=sys.stderr)
    if "--no-open" not in sys.argv:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
