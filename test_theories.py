"""네트워크 없이 도는 검증. python test_theories.py"""
import json, types

import theories


def test_backbone_keeps_only_widely_shared_references():
    """4편 미만이 인용한 문헌은 backbone이 아니라 그냥 참고문헌이다.
    이 하한이 없으면 우연히 겹친 문헌이 '이 분야의 토대'로 둔갑한다."""
    def fake_oa(**p):
        if "openalex_id" in p.get("filter", ""):
            return {"results": [{"id": "W1", "title": "What is AI Literacy?",
                                 "publication_year": 2020, "cited_by_count": 900,
                                 "doi": "https://doi.org/10.1/x",
                                 "open_access": {"is_oa": True},
                                 "best_oa_location": {"pdf_url": "https://x.example/a.pdf"}}]}
        return {"results": [{"id": f"P{i}", "referenced_works": ["W1"] + (["W2"] if i < 2 else [])}
                            for i in range(5)]}
    theories.weekly.oa = fake_oa

    bb, n = theories.backbone()
    assert [b["title"] for b in bb] == ["What is AI Literacy?"]   # W2는 2편뿐이라 탈락
    assert bb[0]["co_cited_here"] == 15          # 갈래 3개 x 5편


def test_identify_parses_json_even_with_fences():
    """모델이 ```json 펜스를 붙이는 경우가 있다."""
    theories.run_claude = lambda p: '```json\n[{"name":"구성주의","one_line":"만들며 배운다",'\
                                    '"source_titles":["Papert"]}]\n```'
    got = theories.identify([{"title": "Papert"}])
    assert got[0]["name"] == "구성주의"


def test_identify_forbids_inventing_theories():
    """LLM이 아는 이론을 늘어놓으면 이 도구의 존재 이유가 없다."""
    assert "근거가 없는 이론은 만들지 마라" in theories.IDENTIFY
    assert "2편 미만이면 넣지 마라" in theories.IDENTIFY


def test_one_theory_per_page_and_practice_first():
    """한 장에 여러 이론을 몰아넣으면 ELI5가 잘하는 걸 못 한다."""
    assert "이 이론 하나만 다룬다" in theories.SECTIONS
    assert "초등 교실에서는" in theories.SECTIONS
    assert "가장 중요한 섹션" in theories.SECTIONS      # 실천이 주인공
    assert "중요하다" in theories.SECTIONS              # 두루뭉술한 마무리 금지 조항


def test_explain_passes_only_that_theorys_sources():
    """다른 이론의 문헌이 섞이면 설명이 흐려진다."""
    seen = {}
    theories.run_claude = lambda p: seen.update(prompt=p) or "<!--TITLE: 구성주의-->\n<h2>x</h2>"
    bb = [{"title": "Papert 1980"}, {"title": "Wing 2006"}]
    title, doc = theories.explain({"name": "구성주의", "one_line": "만들며 배운다",
                                   "source_titles": ["Papert 1980"]}, bb)
    assert "Papert 1980" in seen["prompt"] and "Wing 2006" not in seen["prompt"]
    assert title == "구성주의" and "<h1>구성주의</h1>" in doc


def test_name_slug_keeps_the_whole_name():
    """회귀: eli5.slug()는 URL·경로용이라 '/'를 경로 구분자로 보고 뒷부분만 취한다.
    이론 이름에 '/'가 흔해서(Constructionist / learning-by-design) 앞이 통째로 잘렸다."""
    n = theories.name_slug("Constructionist / learning-by-design approaches to ML")
    assert n.startswith("Constructionist"), n
    assert theories.name_slug("Teacher co-design / 자기결정성 기반").startswith("Teacher")
    assert "자기결정성" in theories.name_slug("Teacher co-design / 자기결정성 기반")
    assert "/" not in n and "\\" not in n          # 파일명으로 안전해야 한다


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
