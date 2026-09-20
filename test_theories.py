"""네트워크 없이 도는 검증. python test_theories.py"""
import types

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
        # W1은 5편이, W2는 2편이 인용
        return {"results": [{"id": f"P{i}", "referenced_works": ["W1"] + (["W2"] if i < 2 else [])}
                            for i in range(5)]}
    theories.weekly.oa = fake_oa

    bb, n = theories.backbone()
    assert [b["title"] for b in bb] == ["What is AI Literacy?"]   # W2는 2편뿐이라 탈락
    assert bb[0]["co_cited_here"] == 15          # 갈래 3개 x 5편
    assert bb[0]["links"]["pdf"] == "https://x.example/a.pdf"


def test_task_forbids_inventing_theories():
    """LLM이 아는 이론을 늘어놓으면 이 도구의 존재 이유가 없다 - 데이터 근거가 있어야 한다."""
    assert "지어내지 마라" in theories.TASK
    assert "근거가 없으면 쓰지 마라" in theories.TASK
    assert "초등 교실에서는" in theories.TASK      # 교사 관점이 빠지면 그냥 이론 나열이다
    assert "한계" in theories.TASK                 # 표본 편향을 밝히게


def test_prompt_reuses_eli5_design_and_diagrams():
    """지도는 그림이 핵심이다. eli5의 SVG 규칙을 그대로 쓴다."""
    from eli5 import DESIGN, DIAGRAMS
    assert "artifact-design" in DESIGN
    assert "반드시 <svg>" in DIAGRAMS


if __name__ == "__main__":
    for name, fn in sorted(vars().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
