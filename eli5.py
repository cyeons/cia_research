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

# 설계 메모: 이전 버전은 학술 섹션 7개를 글로 꽉 채우도록 지시해서, 그림이 비집고
# 들어갈 자리가 없었다. anthropics/claude-plugins-community 의 eli5 스킬은 전체가
# 한 문장이다: "big pictures and few words". 그래서 그림 섹션을 맨 앞에 놓고
# 주 산출물로 삼는다. 뒤의 학술 층은 그 다음이다.

RULES = """너는 초등 컴퓨터교육·AI교육을 공부하는 대학원생의 논문 읽기 도우미다.
논문을 '요약'하지 말고 '이해시켜라'.

# 큰 원칙: 큰 그림, 적은 글자
그림이 설명을 하고 글은 그림을 거든다. 반대가 되면 실패다.
분량으로 성실함을 증명하려 들지 마라. 덜 쓰고 더 이해시켜라.

# 난이도
마지막 '연구적 위치' 섹션을 빼면 전부 중학생이 사전 없이 읽을 수 있어야 한다.
- 논문의 문장을 옮기지 마라. 네 말로 다시 써라. 방법 섹션을 받아쓰면 실패다.
- 전문용어 금지. 꼭 필요하면 쉬운 말로 풀고 원어는 괄호에 넣어라.
  나쁨: "내용타당도비 절단값은 CVR 0.62다"
  좋음: "전문가 10명에게 보여주고 절반 넘게 '꼭 필요하다'고 한 문항만 남겼다"
  나쁨: "정규성을 만족하지 않으면 Mann-Whitney U 검정으로 대체한다"
  좋음: "점수가 한쪽으로 치우쳐 있으면 다른 계산법으로 바꿔 비교한다"
- '유의미한 차이' -> '우연이라고 보기 어려울 만큼 차이가 났다'
- 한 문장에 한 가지만. 한 문단은 3문장까지.
- 기관명·소프트웨어·보고지침 약자(SPSS, NVivo, COREQ)를 나열하지 마라.

# 정직함
원문에 없는 내용을 지어내지 마라. 확인 안 되면 '논문에 없음'이라 쓰고 넘어가라.
억지로 채우지 마라. 짧아도 된다.

# 출력 형식
첫 줄은 반드시 이 형식의 주석 하나다(페이지 제목으로 쓴다):
<!--TITLE: 논문 내용을 알려주는 짧은 한국어 제목-->
그 다음 줄부터 HTML 조각(<h2>/<h3>/<p>/<ul>/<table>/<figure>)만. 인사말 금지.
<html>/<body> 태그와 마크다운 코드펜스(```)도 쓰지 마라.

강조는 아래 클래스만(이미 정의돼 있다. 새 class나 style 속성을 만들지 마라):
- <span class="key">핵심 용어</span> — 형광펜. 섹션당 최대 2개.
- <span class="num">198명</span> — 수치.
- <div class="callout">…</div> — 한 줄 핵심. 섹션당 최대 1개.
- <div class="warn">…</div> — 주의. 문서 전체에서 최대 2개.
- <strong> — 문장 안의 중요한 구절."""

DIAGRAMS = """# 그림 (이 작업의 핵심 산출물)
**최소 3개, 최대 5개.** 그림 없이 끝내면 실패다.

## 무엇을 그리나
1. **개념 그림 — 최소 1개 필수.** 처음 듣는 사람 머릿속에 그림이 안 그려지는
   개념을 골라 그려라. 비유를 그려도 된다(트램펄린 위의 공, 깔때기, 저울).
   본문에서 비유를 들었다면 그 비유를 그려라. 글로 설명한 것을 그림이 받쳐 준다.
2. **원인 그림.** 두 조건을 비교하는 논문이라면, 결과 숫자가 아니라
   그 차이가 '무엇 때문에' 생기는지 구조를 나란히 그려라.
3. **수치 비교.** 막대 두세 개로 크기 차이를 눈에 보이게. 표의 숫자보다 빠르다.

## 절대 하지 말 것
- 문자로 도형을 흉내내지 마라. █ ▏ ■ ─ │ 를 막대나 선으로 쓰는 것은 금지다.
  글꼴 따라 폭이 달라지고 메일에서 깨진다. 도형은 **반드시 <svg>** 다.
- 그림 대신 표로 때우지 마라. 표는 표대로 쓰고 그림은 따로 그린다.
- 이름만 적은 상자를 나열하지 마라. 무엇이 어디로 가는지를 그려라.

## 기술 규칙
- <figure><svg viewBox="0 0 W H" role="img" aria-label="이 그림이 말하는 것">…</svg>
  <figcaption>이 그림이 말하는 것 한 문장</figcaption></figure>
- 크게 그려라. viewBox 너비 600~720, 높이 200~340. 한 그림에 요소는 적게.
- 글자는 14~16px. 한두 단어. 설명 문장은 figcaption으로 내려라.
- 선·글자·화살표는 전부 currentColor. 밝은 배경과 어두운 배경 양쪽에서 읽혀야 한다.
  강조할 요소 딱 하나에만 실제 색을 쓰되 #2da44e, #3b82f6, #d29922 정도의 중간 밝기로.
- 화살표는 <defs><marker>나 작은 <polygon>. 이미지·외부 링크 금지.
- 화살표엔 라벨을 붙여라. 라벨 없는 화살표는 '뭔가 관련 있음'일 뿐이다.
- 막대는 <rect>. 길이를 값에 비례시키고 끝에 <text>로 수치를 적어라.
- 요소를 격자에 맞춰라. 눈대중으로 어긋난 간격은 지저분해 보인다.
- svg 안에 <script>, <style>, <foreignObject> 금지."""

SECTIONS = """논문을 다 읽은 뒤 아래 순서대로 쓴다. 한국어.

<h2>그림으로 보는 핵심</h2>
이 문서의 主다. 그림 3~5개를 여기에 놓고, 그림마다 아래에 1~2문장만 붙여라.
이 섹션만 보고도 논문이 무슨 말인지 알아야 한다. 글을 길게 쓰지 마라.

<h2>세 줄 요약</h2>
<div class="callout">이 논문이 말하는 것 한 줄.</div>
이어서 <ul>로 핵심 3개, 각 한 문장.

<h2>어떤 연구인가</h2>
저자가 풀려던 문제를 3문장 이내로. 이어서 <table>로 정리:
누구에게 / 몇 명 / 얼마 동안 / 무엇을 시켰나 / 무엇을 쟀나.
표 바깥 설명은 3문장 이내. 절차를 나열하지 말고 이 방법의 '핵심 아이디어' 하나만 짚어라.

<h2>무엇을 알아냈나</h2>
핵심 결과 3~5개를 <ul>로. 각 항목은 쉬운 말 한 문장 + 괄호에 수치.

<h2>초등 현장에 주는 시사점</h2>
수업에 옮길 수 있는 것과, 이 논문만으로는 아직 말할 수 없는 것을 나눠서. 각 3개 이내.

<h2>한계와 조심할 점</h2>
저자가 밝힌 것과 네가 보기에 걸리는 것을 구분해서. 3개 이내.

<h2>연구적 위치</h2>
여기서만 학술 용어를 써도 된다. 어떤 이론적 틀에 서 있고 어떤 선행연구를 딛고 있는지.
반복 인용되는 핵심 문헌 3~6개를 <ul>로, 각각 이 논문에서 어떤 역할인지 한 줄씩."""


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


def build_prompt(src):
    """네 조각을 합친다.

    한 번 DIAGRAMS를 빠뜨린 채로 돌아간 적이 있다. 파일에 상수가 있는지가 아니라
    프롬프트에 들어갔는지를 확인해야 한다. 그래서 조립을 함수로 빼서 테스트한다.
    """
    return "\n\n".join([RULES, DIAGRAMS, source_instruction(src), SECTIONS])


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


def split_title(fragment, fallback):
    """모델이 첫 줄에 넣은 제목을 빼낸다. DOI를 제목으로 쓰면 읽을 수 없다."""
    m = re.match(r"\s*<!--\s*TITLE:\s*(.+?)\s*-->", fragment)
    return (m.group(1), fragment[m.end():]) if m else (fallback, fragment)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    prompt = build_prompt(src)
    print(f"읽는 중: {src}", file=sys.stderr)

    title, fragment = split_title(run_claude(prompt), slug(src).replace("_", " "))
    origin = src if src.startswith("http") else Path(src).resolve().as_uri()
    doc = render(f'<p style="font-size:.9em">원문: <a href="{origin}">{src}</a></p>{fragment}',
                 title=title)

    os.makedirs("eli5", exist_ok=True)
    out = Path("eli5") / f"{slug(src)}.html"
    out.write_text(doc, encoding="utf-8")
    print(f"저장: {out}", file=sys.stderr)
    if "--no-open" not in sys.argv:
        webbrowser.open(out.resolve().as_uri())


if __name__ == "__main__":
    main()
