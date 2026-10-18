"""카테고리 템플릿을 기획서/프롬프트에 붙이는 도우미.

main.py 를 import 하지 않고 DB 연결 함수(connect)만 받아서 쓰므로, batch_plans.py 에서 순환 import 없이 쓸 수 있다.

batch_plans.py 사용 예 (기획서를 쓰는 Gemini 프롬프트를 만들기 직전에):

    import plan_templates
    ...
    tpl = plan_templates.template_block(connect, "celeb")   # connect 는 run_once(connect=...) 로 받은 함수
    prompt = prompt + "\\n\\n" + tpl                          # 템플릿이 없으면 '참조 템플릿: 없음' 문단이 붙는다
"""
import json

LABELS = {"celeb": "연예인"}


def load(connect, category: str = "celeb", label: str = "", limit: int = 3):
    """(프롬프트 문단, 템플릿 영상 제목 목록)을 돌려준다. 템플릿이 없으면 제목 목록은 빈 리스트."""
    label = label or LABELS.get(category, category)
    rows = []
    try:
        from psycopg2.extras import RealDictCursor
        conn = connect()
        try:
            with conn, conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """SELECT title, template FROM shorts_templates WHERE category = %s
                       ORDER BY updated_at DESC, id DESC LIMIT %s""",
                    (category, limit),
                )
                rows = cur.fetchall()
        finally:
            conn.close()
    except Exception:
        rows = []  # 템플릿 조회에 실패해도 기획서 작성은 계속한다
    if not rows:
        return (f"참조 템플릿: 없음({label} 카테고리에 등록된 템플릿이 없다). "
                "일반적인 쇼츠 문법(훅 → 전개 → 마무리)으로 구성하라."), []
    out = [f"참조 템플릿({label} 카테고리). 아래 쇼츠의 화면 구성, 자막 위치·글자 크기, 후킹 대사 문형, "
           "시나리오 멘트의 톤과 흐름을 따르되 문장은 그대로 베끼지 말고 이번 소재에 맞게 바꿔라. "
           "기획서의 구성안과 연출·자막에 화면 구성, 자막 위치·크기, 후킹 대사, 시나리오 멘트를 포함하라:"]
    for r in rows:
        out.append(f"- 템플릿 영상: {r['title']}\n{json.dumps(r['template'], ensure_ascii=False)[:2500]}")
    return "\n".join(out), [r["title"] for r in rows]


def template_block(connect, category: str = "celeb", label: str = "", limit: int = 3) -> str:
    return load(connect, category, label, limit)[0]
