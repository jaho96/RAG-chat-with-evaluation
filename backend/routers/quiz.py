import asyncio
import json
import random
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.llm import get_llm
import services.vector_store as vs

router = APIRouter(prefix="/quiz", tags=["quiz"])


class GenerateRequest(BaseModel):
    doc_ids: list[str]      # 빈 리스트면 전체 문서 사용
    count: int = 10
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"


class GradeRequest(BaseModel):
    question: str
    correct_answer: str
    user_answer: str
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"


def _collect_stream(llm, system_prompt: str, user_message: str) -> str:
    """스트리밍 토큰을 모아 하나의 문자열로 반환"""
    return "".join(llm.chat_stream(system_prompt, [{"role": "user", "content": user_message}]))


async def _collect_stream_async(llm, system_prompt: str, user_message: str) -> str:
    """블로킹 LLM 호출을 별도 스레드에서 실행 — 이벤트 루프 차단 방지"""
    return await asyncio.to_thread(_collect_stream, llm, system_prompt, user_message)


def _get_chunks_for_docs(doc_ids: list[str], sample: int = 30) -> list[str]:
    """선택한 문서들의 청크 텍스트를 샘플링해서 반환"""
    all_chunks = vs.get_chunks_text(doc_ids)

    if not all_chunks:
        return []

    # 너무 짧은 청크 제거
    all_chunks = [c for c in all_chunks if len(c.strip()) > 100]

    # 랜덤 샘플링
    return random.sample(all_chunks, min(sample, len(all_chunks)))


def _extract_json(text: str) -> list:
    """LLM 응답에서 JSON 배열 추출"""
    # ```json ... ``` 블록 처리
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if match:
        return json.loads(match.group(1))

    # 직접 [ ... ] 찾기
    match = re.search(r"(\[[\s\S]*\])", text)
    if match:
        return json.loads(match.group(1))

    raise ValueError("JSON 배열을 찾을 수 없습니다.")


@router.post("/generate")
async def generate_quiz(req: GenerateRequest):
    if not vs.list_documents():
        raise HTTPException(status_code=404, detail="문서를 먼저 업로드해주세요.")

    chunks = _get_chunks_for_docs(req.doc_ids)
    if not chunks:
        raise HTTPException(status_code=404, detail="선택한 문서에서 내용을 찾을 수 없습니다.")

    context = "\n\n---\n\n".join(chunks)

    short_count = req.count // 2
    multi_count = req.count - short_count

    system_prompt = (
        "당신은 문서 기반 퀴즈를 만드는 전문가입니다.\n"
        "아래 문서 내용을 바탕으로 퀴즈를 만들어 주세요.\n"
        "반드시 문서에 있는 내용만 사용하세요.\n\n"
        "출력 형식: JSON 배열만 출력하세요. 다른 텍스트는 절대 포함하지 마세요.\n\n"
        "각 항목 형식:\n"
        "단답형: {\"type\": \"short\", \"question\": \"...\", \"answer\": \"...\", \"explanation\": \"...\"}\n"
        "객관식: {\"type\": \"multiple\", \"question\": \"...\", \"options\": [\"A\", \"B\", \"C\", \"D\"], \"answer\": \"정답 텍스트\", \"explanation\": \"...\"}\n\n"
        f"[문서 내용]\n{context}"
    )

    user_message = (
        f"단답형 {short_count}개, 객관식 4지선다 {multi_count}개를 만들어주세요. "
        f"총 {req.count}개. JSON 배열만 출력하세요."
    )

    llm = get_llm(req.provider, req.model)

    try:
        raw = await _collect_stream_async(llm, system_prompt, user_message)
        questions = _extract_json(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"퀴즈 생성 실패: {str(e)}")

    # 필드 검증 및 id 부여
    valid = []
    for i, q in enumerate(questions):
        if not q.get("question") or not q.get("answer"):
            continue
        q["id"] = i + 1
        if q.get("type") == "multiple" and not q.get("options"):
            q["type"] = "short"
        valid.append(q)

    if not valid:
        raise HTTPException(status_code=500, detail="유효한 문제를 생성하지 못했습니다.")

    return {"questions": valid}


@router.post("/grade")
async def grade_answer(req: GradeRequest):
    """단답형 답변 채점 — LLM이 의미 기반으로 평가"""
    system_prompt = (
        "당신은 퀴즈 채점관입니다.\n"
        "사용자의 답변이 정답과 의미상 일치하는지 판단하세요.\n"
        "완전히 같지 않아도 핵심 내용이 맞으면 정답으로 처리하세요.\n\n"
        "반드시 JSON만 출력하세요: {\"correct\": true/false, \"feedback\": \"짧은 해설\"}"
    )
    user_message = (
        f"문제: {req.question}\n"
        f"정답: {req.correct_answer}\n"
        f"사용자 답변: {req.user_answer}\n\n"
        "채점 결과를 JSON으로 출력하세요."
    )

    llm = get_llm(req.provider, req.model)

    try:
        raw = await _collect_stream_async(llm, system_prompt, user_message)
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise ValueError("JSON 없음")
        result = json.loads(match.group())
        return {
            "correct": bool(result.get("correct", False)),
            "feedback": result.get("feedback", ""),
        }
    except Exception:
        # 채점 실패 시 단순 문자열 비교로 폴백
        correct = req.user_answer.strip() in req.correct_answer or req.correct_answer in req.user_answer.strip()
        return {"correct": correct, "feedback": f"정답: {req.correct_answer}"}
