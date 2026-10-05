import json
import time
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from services.embedder import embed_query
import services.vector_store as vs
from services.llm import get_llm, get_available_models
from services.query_rewriter import prepare_queries
from services.readability_evaluator import evaluate_async
from services.langsmith_tracer import RAGTrace
from services.trace_store import save_trace, update_feedback
from services.cache import get_response, set_response
import services.history_manager as hm

router = APIRouter(prefix="/chat", tags=["chat"])


class HistoryMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    top_k: int = 7
    history: list[HistoryMessage] = []


class FeedbackRequest(BaseModel):
    trace_id: str
    feedback: int  # 1 = 👍, -1 = 👎


# ── 메타 쿼리 감지 ─────────────────────────────────────────────────

META_PATTERNS = {
    "list_docs": ["어떤 자료", "무슨 자료", "자료 목록", "문서 목록", "어떤 문서",
                  "무슨 문서", "자료 뭐야", "데이터 뭐야", "가지고 있는 자료",
                  "가지고 있는 데이터", "자료가 뭐", "문서가 뭐"],
    "count_docs": ["몇 개", "몇개", "총 몇", "문서 개수", "자료 개수"],
    "recent_docs": ["최근에 추가", "마지막으로 추가", "최근 문서", "최근 자료"],
    "topics":     ["어떤 주제", "무슨 주제", "주제 뭐", "어떤 내용을 알아", "뭘 알아"],
    "summarize":  ["요약", "정리해줘", "내용 알려줘", "전체 내용", "어떤 내용이야"],
}


def detect_meta(question: str) -> str | None:
    q = question.strip()
    for meta_type, keywords in META_PATTERNS.items():
        if any(kw in q for kw in keywords):
            return meta_type
    return None


def handle_meta(meta_type: str) -> str:
    docs = vs.list_documents()

    if meta_type == "list_docs":
        if not docs:
            return "현재 업로드된 문서가 없습니다."
        lines = [f"- {d['filename']}" for d in docs]
        return f"현재 보유 중인 문서 {len(docs)}개입니다:\n" + "\n".join(lines)

    if meta_type == "count_docs":
        return f"현재 총 {len(docs)}개의 문서가 있습니다."

    if meta_type == "recent_docs":
        if not docs:
            return "현재 업로드된 문서가 없습니다."
        recent = docs[:3]
        lines = [f"- {d['filename']} ({d['uploaded_at'][:10]})" for d in recent]
        return "최근 추가된 문서입니다:\n" + "\n".join(lines)

    return "알 수 없는 메타 쿼리입니다."


# ── 엔드포인트 ────────────────────────────────────────────────────

@router.get("/models")
def list_models():
    return get_available_models()


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    if req.feedback not in (1, -1):
        raise HTTPException(status_code=400, detail="feedback must be 1 or -1")
    update_feedback(req.trace_id, req.feedback)
    return {"ok": True}


@router.post("/stream")
def chat_stream(req: ChatRequest):
    if not vs.list_documents():
        raise HTTPException(status_code=404, detail="문서를 먼저 업로드해주세요.")

    # ── 메타 쿼리 처리 ───────────────────────────────────────────
    meta_type = detect_meta(req.question)
    if meta_type == "topics":
        import random as _random
        chunks = vs.get_chunks_text([])
        chunks = [c for c in chunks if len(c.strip()) > 100]
        sampled = _random.sample(chunks, min(20, len(chunks)))
        context = "\n\n---\n\n".join(sampled)
        llm = get_llm(req.provider, req.model)
        system_prompt = (
            "당신은 문서 분석 전문가입니다.\n"
            "아래 문서 내용을 읽고 핵심 주제들을 간결하게 정리해주세요.\n"
            "주제는 bullet point로 5~10개 이내로 요약하세요."
        )
        user_msg = f"[문서 내용]\n{context}\n\n이 문서들의 핵심 주제를 정리해줘."

        def topics_generate():
            trace_id = str(uuid.uuid4())
            yield f"data: {json.dumps({'type': 'trace_id', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': []}, ensure_ascii=False)}\n\n"
            for token in llm.chat_stream(system_prompt, [{"role": "user", "content": user_msg}]):
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(topics_generate(), media_type="text/event-stream")

    if meta_type == "summarize":
        import random as _random
        chunks = vs.get_chunks_text([])
        chunks = [c for c in chunks if len(c.strip()) > 100]
        sampled = _random.sample(chunks, min(30, len(chunks)))
        context = "\n\n---\n\n".join(sampled)
        llm = get_llm(req.provider, req.model)
        system_prompt = (
            "당신은 문서 요약 전문가입니다.\n"
            "아래 문서 내용을 읽고 전체 내용을 체계적으로 요약해주세요.\n"
            "문서가 여러 개면 각 문서별로 나누어 요약하고, 전체 핵심 내용을 마지막에 정리해주세요."
        )
        user_msg = f"[문서 내용]\n{context}\n\n문서 전체 내용을 요약해줘."

        def summarize_generate():
            trace_id = str(uuid.uuid4())
            yield f"data: {json.dumps({'type': 'trace_id', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': []}, ensure_ascii=False)}\n\n"
            for token in llm.chat_stream(system_prompt, [{"role": "user", "content": user_msg}]):
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(summarize_generate(), media_type="text/event-stream")

    if meta_type:
        answer = handle_meta(meta_type)

        def meta_generate():
            trace_id = str(uuid.uuid4())
            yield f"data: {json.dumps({'type': 'trace_id', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': []}, ensure_ascii=False)}\n\n"
            for ch in answer:
                yield f"data: {json.dumps({'type': 'token', 'content': ch}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(meta_generate(), media_type="text/event-stream")

    # ── 응답 캐시 확인 ────────────────────────────────────────────
    cached = get_response(req.question)
    if cached:
        def cache_generate():
            trace_id = str(uuid.uuid4())
            yield f"data: {json.dumps({'type': 'trace_id', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'sources', 'sources': cached['sources']}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'cache_hit', 'content': True}, ensure_ascii=False)}\n\n"
            for word in cached["answer"].split(" "):
                yield f"data: {json.dumps({'type': 'token', 'content': word + ' '}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(cache_generate(), media_type="text/event-stream")

    # ── RAG 스트리밍 ──────────────────────────────────────────────
    llm = get_llm(req.provider, req.model)

    def generate():
        full_answer = ""
        trace_id = str(uuid.uuid4())
        trace = None
        sources = []
        start_time = time.time()
        try:
            # 검색 시작 즉시 알림 — HyDE 처리 중 사용자에게 상태 표시
            yield f"data: {json.dumps({'type': 'status', 'content': 'searching'}, ensure_ascii=False)}\n\n"

            # rewrite(키워드 검색용) + HyDE(벡터 검색용) 병렬 실행
            keyword_query, hyde_text = prepare_queries(req.question, req.provider, req.model)
            query_embedding = embed_query(hyde_text)
            sources = vs.search(query_embedding, query_text=keyword_query, top_k=req.top_k)

            if not sources:
                yield f"data: {json.dumps({'type': 'error', 'content': '관련 내용을 문서에서 찾지 못했습니다.'}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            context = "\n\n---\n\n".join(
                f"[출처: {s['metadata']['filename']} / 청크 #{s['metadata']['chunk_index']}]\n{s['text']}"
                for s in sources
            )
            system_prompt = (
                "당신은 업로드된 문서를 기반으로 질문에 답변하는 AI 어시스턴트입니다.\n"
                "아래 규칙을 반드시 따르세요:\n"
                "1. 반드시 제공된 참고 문서 내용만을 근거로 답변하세요.\n"
                "2. 문서에 없는 내용은 절대 추측하거나 지어내지 말고 '문서에서 찾을 수 없습니다.'라고 답하세요.\n"
                "3. 답변은 문서의 내용을 충실히 반영하되, 자연스럽고 이해하기 쉽게 서술하세요.\n"
                "4. 관련 내용이 여러 청크에 나뉘어 있으면 통합하여 완전한 답변을 제공하세요.\n"
                "5. 이전 대화 맥락이 있으면 참고하여 자연스럽게 이어서 답변하세요.\n"
                "6. 답변은 마크다운으로 구조화하세요:\n"
                "   - 여러 개념·단계를 설명할 때는 ## 소제목으로 구분하세요\n"
                "   - 나열할 내용은 불릿(-), 순서가 있으면 번호(1.)를 사용하세요\n"
                "   - 핵심 용어·중요 내용은 **굵게** 강조하세요\n"
                "   - 단답형 질문에는 간결하게, 복잡한 질문에는 구조적으로 답하세요\n\n"
                f"[참고 문서]\n{context}"
            )
            all_messages = [
                {"role": m.role, "content": m.content}
                for m in req.history
            ] + [{"role": "user", "content": req.question}]
            managed_messages = hm.prepare(all_messages, llm)

            trace = RAGTrace(question=req.question, provider=req.provider, model=req.model)
            trace.start()
            trace.log_retrieval(sources)
            trace.log_llm_start(system_prompt)

            yield f"data: {json.dumps({'type': 'trace_id', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"

            sources_data = [
                {
                    "filename": s["metadata"]["filename"],
                    "chunk_index": s["metadata"]["chunk_index"],
                    "score": round(s["score"], 3),
                    "page": s["metadata"].get("page") if s["metadata"].get("page", -1) != -1 else None,
                }
                for s in sources
            ]
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources_data}, ensure_ascii=False)}\n\n"

            start_time = time.time()
            for token in llm.chat_stream(system_prompt, managed_messages):
                trace.add_token(token)
                full_answer += token
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"

            elapsed_ms = int((time.time() - start_time) * 1000)
            trace.finish()
            save_trace(trace_id, req.question, full_answer, req.provider, req.model, elapsed_ms, sources)
            set_response(req.question, full_answer, sources_data)
            evaluate_async(full_answer, req.provider, req.model, trace_id)
            yield "data: [DONE]\n\n"

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            if trace:
                trace.finish(error=str(e))
            save_trace(trace_id, req.question, full_answer or None, req.provider, req.model, elapsed_ms, sources, error=str(e))
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")