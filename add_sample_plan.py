"""테스트용 샘플 기획서를 서버에 등록한다.
사용법:  python add_sample_plan.py [서버주소]     (기본값 http://localhost:8000)
PLANS_INGEST_KEY 환경변수를 서버에 설정했다면, 이 스크립트를 실행하는 쪽에도 같은 값을 환경변수로 넣어 주세요.
"""
import os
import sys

import httpx

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")

plan = {
    "title": "[샘플] 가상 가수 '하늘', 데뷔 5주년 깜짝 팬미팅 발표",
    "celebrity": "가상 가수 하늘 (샘플)",
    "source_type": "news",
    "source_url": "",  # 비워 두면 여러 번 실행해도 계속 등록된다
    "source_title": "샘플 기사 제목",
    "summary": "테스트용 가짜 기획서예요. 목록과 상세 화면, 승인·삭제 버튼이 잘 동작하는지 확인하는 용도입니다.",
    "planning_doc": (
        "# 하늘, 데뷔 5주년 깜짝 팬미팅\n\n"
        "## 컨셉\n- 팬들이 가장 궁금해할 **발표 순간**을 15초로 압축\n- 훅: \"5주년에 이런 발표를?\"\n\n"
        "## 구성안\n"
        "| 시간 | 장면 | 자막 |\n|---|---|---|\n"
        "| 0~3초 | 발표 장면 클로즈업 | 5주년 깜짝 발표! |\n"
        "| 3~10초 | 팬 반응, 일정 정리 | 일정은 이렇게 |\n"
        "| 10~15초 | 마무리 | 댓글로 의견 남겨주세요 |\n\n"
        "## 제작 체크리스트\n- 출처 표기\n- 저작권 확인된 이미지만 사용\n"
    ),
}

r = httpx.post(f"{BASE}/api/plans", json=plan, headers={"X-API-Key": os.environ.get("PLANS_INGEST_KEY", "")}, timeout=15)
print(r.status_code, r.text[:300])
