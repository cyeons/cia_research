"""논문 하나를 ELI5 HTML로 만들어 브라우저에 띄운다.

    python eli5.py paper.pdf
    python eli5.py https://doi.org/10.1371/journal.pone.0345347

로컬 Claude Code(`claude -p`)를 헤드리스로 부른다. 구독으로 처리되므로 API 키가 필요 없다.
웹 주소는 WebFetch가 읽는다. PDF는 우리가 PyMuPDF로 직접 텍스트를 뽑아 프롬프트에 넣는다
(Claude Code의 Read 도구에 맡기지 않는다 — 아래 참고).
"""
import os, re, shutil, subprocess, sys, urllib.parse, webbrowser
from pathlib import Path

try:
    import fitz  # pymupdf. pip install pymupdf, 관리자 권한 불필요.
except ImportError:
    fitz = None

from weekly import render          # 메일 브리핑과 같은 인쇄용 스타일을 그대로 쓴다

MODEL = "opus"
MAX_TURNS = "20"

# PDF를 왜 Read 도구가 아니라 우리가 직접 뽑는가:
#   1) Claude Code의 Read 도구는 PDF를 페이지 이미지로 렌더링하는 데 pdftoppm(poppler)이
#      필요하다. 관리자 권한 없는 환경(choco install도 막힘)에는 없을 수 있다.
#   2) 이 대체 경로로 pdftotext를 시도해도, Windows Git/MSYS2에 흔히 딸려오는 버전은
#      2017년 xpdf 4.00이라 한글 CID 폰트 매핑을 못 읽는다 — 한글이 통째로 사라진다
#      (실제로 겪음: 96,447자를 뽑았는데 한글이 0글자였다).
#   3) PyMuPDF(pip, 관리자 권한 불필요)는 둘 다 필요 없고 한글도 정확히 뽑는다.
# 전문을 통째로 프롬프트에 넣으므로, 페이지를 나눠 여러 번 Read할 필요도 없어진다.

# 설계 메모: 이전 버전은 학술 섹션 7개를 글로 꽉 채우도록 지시해서, 그림이 비집고
# 들어갈 자리가 없었다. anthropics/claude-plugins-community 의 eli5 스킬은 전체가
# 한 문장이다: "big pictures and few words". 그래서 그림 섹션을 맨 앞에 놓고
# 주 산출물로 삼는다. 뒤의 학술 층은 그 다음이다.

DESIGN = """# 먼저 할 일 — 디자인
Skill 도구로 `artifact-design` 스킬을 로드하고, 그 지침대로 이 페이지를 디자인해라.
글을 쓰기 전에 먼저 한다.

- 이 논문의 주제에서 끌어낸 팔레트 4~6색과 짝지은 글꼴을 정해라.
  조각 맨 앞에 Google Fonts <link>와 <style> 블록을 직접 써라.
- 색은 :root에 토큰으로 정의하고 @media (prefers-color-scheme: dark)로 다시 정의해라.
  두 배경 모두 설계해라. 단순히 뒤집지 마라.
- .key / .num / .callout / .warn / figure / figcaption 클래스가 이미 있다.
  네 팔레트에 맞게 다시 스타일링해라.
- 본문 너비는 한 줄 65자 안팎. 제목에 text-wrap: balance.
- 인쇄용 @media print 규칙은 이미 들어 있다. 덮어쓰지 마라.
- SVG 안의 currentColor가 네 본문 색을 물려받도록 색 토큰을 맞춰라.
- 흔한 AI 기본값은 피해라: 크림색 배경+세리프+테라코타, 보라-파랑 그라디언트,
  Inter/Space Grotesk, 이모지 섹션 마커, 전부 가운데 정렬, 모든 블록에 같은 둥근 카드.

아티팩트로 발행하지 마라. HTML 조각만 출력해라.

스킬 로드가 "Unknown skill" 등으로 실패해도 절대 멈추지 마라. 그 경우 이 문서에 적힌
지침(팔레트/글꼴/다크모드/클래스 재스타일링)을 네가 직접 따라 계속 진행해라."""


RULES = """너는 초등 컴퓨터교육·AI교육을 공부하는 대학원생의 논문 읽기 도우미다.
논문을 '요약'하지 말고 '이해시켜라'.

# 큰 원칙: 쉬운 말로, 충분히 자세히
'쉽게'와 '짧게'는 다른 말이다. 어려운 논문을 쉬운 말로 풀려면 오히려 <b>더 길어야</b> 한다.
전문용어 한 단어를 풀어 쓰면 두세 문장이 되기 때문이다. 그게 정상이다.

읽는 사람은 이 글만 읽고 원문을 안 볼 수도 있다. 논문의 내용이 여기 다 들어와야 한다.
결과를 나열만 하지 말고 <b>왜 그런 결과가 나왔는지</b>까지 설명해라 — 그게 이해다.
분량을 아끼지 마라. 아껴서 생기는 손해가 길어서 생기는 손해보다 크다.

목표 분량: 그림을 뺀 본문이 <b>8,000자 이상</b>. 원문이 짧으면 그만큼만 쓴다.

# 난이도
마지막 '연구적 위치' 섹션을 빼면 전부 중학생이 사전 없이 읽을 수 있어야 한다.
- 논문의 문장을 옮기지 마라. 네 말로 다시 써라. 방법 섹션을 받아쓰면 실패다.
- 전문용어 금지. 꼭 필요하면 쉬운 말로 풀고 원어는 괄호에 넣어라.
  나쁨: "내용타당도비 절단값은 CVR 0.62다"
  좋음: "전문가 10명에게 보여주고 절반 넘게 '꼭 필요하다'고 한 문항만 남겼다"
  나쁨: "정규성을 만족하지 않으면 Mann-Whitney U 검정으로 대체한다"
  좋음: "점수가 한쪽으로 치우쳐 있으면 다른 계산법으로 바꿔 비교한다"
- '유의미한 차이' -> '우연이라고 보기 어려울 만큼 차이가 났다'
- 한 문장에 한 가지만. 한 문단은 3~4문장으로 끊어라(읽기 편하게 나누라는 뜻이지, 적게 쓰라는 뜻이 아니다).
- 기관명·소프트웨어·보고지침 약자(SPSS, NVivo, COREQ)를 나열하지 마라.

# 정직함
원문에 없는 내용을 지어내지 마라. 확인 안 되면 '논문에 없음'이라 쓰고 넘어가라.
없는 것을 지어내서 분량을 채우는 것과, 있는 것을 충분히 설명하는 것은 다르다.
앞은 금지고 뒤는 권장이다.

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

SECTIONS = """아래 순서대로 쓴다. 한국어.

문서가 여러 주제를 모은 것이면(동향 리포트, 매거진, 백서 — 여러 나라·기관·사례가
나열된 것) 같은 틀을 쓰되, 한 꼭지만 붙들지 말고 <b>모든 꼭지를 고르게</b> 다뤄라.
끝에 논문이 한두 편 실려 있다고 그것만 정리하면 실패다. 분량이 많은 쪽이 본체다.

<h2>그림으로 보는 핵심</h2>
이 섹션은 그림이 주인공이다. 그림 3~5개를 놓고, 그림마다 아래에 짧은 설명을 붙여라.
여기만 보고도 논문이 무슨 말인지 알아야 한다. 자세한 이야기는 아래 섹션들에서 한다.

<h2>세 줄 요약</h2>
<div class="callout">이 논문이 말하는 것 한 줄.</div>
이어서 <ul>로 핵심 3개, 각 한 문장. 여기만 짧게 쓴다.

<h2>어떤 연구인가</h2>
저자가 풀려던 문제가 무엇이고 왜 그게 문제인지 충분히 설명해라.
이어서 <table>로 정리: 누구에게 / 몇 명 / 얼마 동안 / 무엇을 시켰나 / 무엇을 쟀나.
표는 한눈에 보라고 있는 것이고, 표 바깥에서 실제로 어떻게 진행됐는지 이야기해라 —
아이들이 무엇을 했는지, 무엇으로 쟀는지, 왜 그렇게 설계했는지.
조사 설계가 하나로 없는 문서(여러 주제를 모은 것)라면 이 표를 억지로 만들지 말고,
대신 무엇을 어디까지 다루는 문서인지를 같은 자리에서 설명해라.

<h2>무엇을 알아냈나</h2>
핵심 결과를 하나씩 <h3>로 나눠 다뤄라. 결과마다 문단 하나 이상 쓴다.
숫자를 적는 것으로 끝내지 마라 — 그 숫자가 무슨 뜻인지, 크다는 건지 작다는 건지,
저자가 그 결과를 어떻게 풀이했는지까지 쉬운 말로 이어서 써라.
논문에 저자의 해석이 있으면 그것도 옮겨라(네 추측과 구분해서).

<h2>초등 현장에 주는 시사점</h2>
수업에 옮길 수 있는 것과, 이 논문만으로는 아직 말할 수 없는 것을 나눠서.
옮길 수 있는 것은 "~할 때 ~하게 하라" 수준으로 구체적으로, 왜 그런지 근거와 함께.

<h2>한계와 조심할 점</h2>
저자가 밝힌 것과 네가 보기에 걸리는 것을 구분해서. 각 항목마다 그 한계가
결과 해석을 어떻게 제한하는지 한 문장 덧붙여라.

<h2>연구적 위치</h2>
여기서만 학술 용어를 써도 된다. 어떤 이론적 틀에 서 있고 어떤 선행연구를 딛고 있는지.
반복 인용되는 핵심 문헌을 <ul>로, 각각 이 논문에서 어떤 역할인지."""


def extract_pdf_text(path):
    """PyMuPDF로 PDF 전문을 뽑는다. 이유는 파일 상단 주석 참고."""
    if fitz is None:
        sys.exit("pymupdf가 설치돼 있지 않습니다. `pip install pymupdf` 후 다시 실행하세요.")
    pages = fitz.open(str(path))
    text = "\n".join(p.get_text() for p in pages)
    if len(text.strip()) < 200:
        sys.exit(f"PDF에서 텍스트가 거의 안 나왔습니다({len(text.strip())}자). "
                 f"스캔본이라 텍스트 층이 없을 수 있습니다: {path}")
    return text


def source_instruction(src):
    """원문을 준비한다. URL은 WebFetch에 맡기고, PDF는 텍스트를 직접 뽑아 통째로 준다."""
    if src.startswith(("http://", "https://")):
        return f"WebFetch로 다음 주소의 논문을 가져와 전문을 읽어라: {src}"
    path = Path(src)
    if not path.is_file():
        sys.exit(f"파일이 없습니다: {src}")
    if path.suffix.lower() != ".pdf":
        sys.exit(f"PDF가 아닙니다: {src} (PDF 파일이나 http(s) 주소를 주세요)")
    text = extract_pdf_text(path)
    return f"다음은 논문 원문 전체다(PDF에서 텍스트로 추출함). 이 내용만 근거로 삼아라:\n\n{text}"


def build_prompt(src):
    """네 조각을 합친다.

    한 번 DIAGRAMS를 빠뜨린 채로 돌아간 적이 있다. 파일에 상수가 있는지가 아니라
    프롬프트에 들어갔는지를 확인해야 한다. 그래서 조립을 함수로 빼서 테스트한다.
    """
    return "\n\n".join([DESIGN, RULES, DIAGRAMS, source_instruction(src), SECTIONS])


def run_claude(prompt):
    exe = shutil.which("claude")
    if not exe:
        sys.exit("`claude` 명령을 찾을 수 없습니다. Claude Code가 설치되고 PATH에 있어야 합니다.")
    # 프롬프트는 반드시 stdin으로. 윈도우의 claude.CMD 셔임을 거치면 argv로 준
    # 멀티라인 문자열이 첫 줄에서 잘린다(조용히, 에러 없이). 그러면 지시 대부분이
    # 사라진 채로 실행돼 엉뚱한 응답이 나온다.
    r = subprocess.run(
        [exe, "-p", "--output-format", "text", "--model", MODEL,
         "--max-turns", MAX_TURNS, "--allowed-tools", "WebFetch,Skill"],
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
