"""
검색 성능 벤치마크 — 기본 검색 vs HyDE + 쿼리 재작성 비교

[기본 검색]  질문 → 임베딩 → 벡터 검색만
[향상 검색]  질문 → (쿼리 재작성 || HyDE 병렬) → 하이브리드 검색(벡터 + 키워드 + RRF)

사용법:
  cd backend
  source venv/bin/activate
  python benchmark.py
  python benchmark.py --questions 10 --top-k 5 --provider gemini --model gemini-2.5-flash
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: F401 — .env 로드
from services.embedder import embed_query
from services.vector_store import search, get_chunks_text
from services.query_rewriter import prepare_queries
from services.llm import get_llm


# ── 질문 자동 생성 ─────────────────────────────────────────────────

_Q_PROMPT = """\
아래 문서 내용을 보고, 이 문서에 대해 사용자가 할 법한 자연스러운 한국어 질문 {n}개를 만들어주세요.
질문은 '~에 대해 알려줘', '~는 뭐야?', '~은 어떻게 해?' 같은 대화체로 작성하세요.
각 질문은 번호 없이 한 줄씩 출력하고, 다른 설명은 하지 마세요.

[문서]
{context}"""


def generate_questions(chunks: list[str], n: int, provider: str, model: str) -> list[str]:
    sampled = random.sample(chunks, min(n * 3, len(chunks)))
    context = "\n\n---\n\n".join(sampled[:n * 2])
    llm = get_llm(provider, model)
    prompt = _Q_PROMPT.format(n=n, context=context[:4000])
    result = "".join(llm.chat_stream("", [{"role": "user", "content": prompt}]))
    questions = [q.strip().lstrip("0123456789.-) ") for q in result.strip().splitlines() if q.strip()]
    return questions[:n]


# ── 검색 실행 ──────────────────────────────────────────────────────

def run_baseline(question: str, top_k: int) -> dict:
    """기본: 질문을 그대로 임베딩 → 벡터 검색만"""
    embedding = embed_query(question)
    results = search(embedding, query_text="", top_k=top_k)
    scores = [r["score"] for r in results]
    return {
        "avg":  round(sum(scores) / len(scores), 4) if scores else 0.0,
        "top1": round(scores[0], 4) if scores else 0.0,
        "hits": len(scores),
    }


def run_enhanced(question: str, top_k: int, provider: str, model: str) -> dict:
    """향상: 쿼리 재작성 + HyDE 병렬 → 하이브리드 검색"""
    keyword_query, hyde_text = prepare_queries(question, provider, model)
    embedding = embed_query(hyde_text)
    results = search(embedding, query_text=keyword_query, top_k=top_k)
    scores = [r["score"] for r in results]
    return {
        "avg":          round(sum(scores) / len(scores), 4) if scores else 0.0,
        "top1":         round(scores[0], 4) if scores else 0.0,
        "hits":         len(scores),
        "keyword_query": keyword_query,
        "hyde_preview":  hyde_text[:80] + "…" if len(hyde_text) > 80 else hyde_text,
    }


# ── 메인 ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RAG 검색 성능 벤치마크")
    parser.add_argument("--questions", type=int, default=5,  help="테스트 질문 수 (기본: 5)")
    parser.add_argument("--top-k",    type=int, default=7,   help="검색 결과 수 (기본: 7)")
    parser.add_argument("--provider", default="gemini",      help="LLM 제공사")
    parser.add_argument("--model",    default="gemini-2.5-flash", help="LLM 모델")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  RAG 검색 성능 벤치마크")
    print(f"  모델: {args.provider}/{args.model}  |  top_k={args.top_k}")
    print(f"{'='*60}\n")

    chunks = get_chunks_text([])
    chunks = [c for c in chunks if len(c.strip()) > 100]
    if not chunks:
        print("❌ 업로드된 문서가 없습니다. 먼저 문서를 업로드하세요.")
        sys.exit(1)

    print(f"✅ 문서 청크 {len(chunks)}개 확인")
    print(f"🤖 테스트 질문 {args.questions}개 자동 생성 중...\n")

    questions = generate_questions(chunks, args.questions, args.provider, args.model)
    if not questions:
        print("❌ 질문 생성 실패")
        sys.exit(1)

    details = []
    for i, q in enumerate(questions, 1):
        print(f"[{i}/{len(questions)}] {q}")

        base = run_baseline(q, args.top_k)
        enh  = run_enhanced(q, args.top_k, args.provider, args.model)

        diff_avg  = enh["avg"]  - base["avg"]
        diff_top1 = enh["top1"] - base["top1"]

        print(f"  기본  — avg: {base['avg']:.1%}  top1: {base['top1']:.1%}")
        print(f"  향상  — avg: {enh['avg']:.1%}  top1: {enh['top1']:.1%}  "
              f"(Δavg {diff_avg:+.1%}  Δtop1 {diff_top1:+.1%})")
        print(f"  키워드: {enh['keyword_query']}")
        print(f"  HyDE:  {enh['hyde_preview']}\n")

        details.append({
            "question":      q,
            "baseline_avg":  base["avg"],
            "baseline_top1": base["top1"],
            "enhanced_avg":  enh["avg"],
            "enhanced_top1": enh["top1"],
            "diff_avg":      round(diff_avg,  4),
            "diff_top1":     round(diff_top1, 4),
            "keyword_query": enh["keyword_query"],
        })

    # ── 요약 ─────────────────────────────────────────────────────────
    n = len(details)
    avg_base_avg  = sum(d["baseline_avg"]  for d in details) / n
    avg_enh_avg   = sum(d["enhanced_avg"]  for d in details) / n
    avg_base_top1 = sum(d["baseline_top1"] for d in details) / n
    avg_enh_top1  = sum(d["enhanced_top1"] for d in details) / n
    improved      = sum(1 for d in details if d["diff_avg"] > 0)

    print("=" * 60)
    print(f"  📊 결과 요약  ({n}개 질문, top_k={args.top_k})")
    print("=" * 60)
    print(f"  {'':20s}  {'기본':>8}  {'향상':>8}  {'개선폭':>8}")
    print(f"  {'-'*48}")
    print(f"  {'평균 관련도 (avg)':20s}  {avg_base_avg:>7.1%}  {avg_enh_avg:>7.1%}  {avg_enh_avg-avg_base_avg:>+7.1%}")
    print(f"  {'Top-1 관련도':20s}  {avg_base_top1:>7.1%}  {avg_enh_top1:>7.1%}  {avg_enh_top1-avg_base_top1:>+7.1%}")
    print(f"  {'향상된 질문 수':20s}  {'':>8}  {improved}/{n}개")
    print("=" * 60)

    out = {
        "config": {
            "questions": n,
            "top_k":     args.top_k,
            "provider":  args.provider,
            "model":     args.model,
        },
        "summary": {
            "baseline_avg_score":  round(avg_base_avg,  4),
            "enhanced_avg_score":  round(avg_enh_avg,   4),
            "diff_avg_score":      round(avg_enh_avg  - avg_base_avg,  4),
            "baseline_top1_score": round(avg_base_top1, 4),
            "enhanced_top1_score": round(avg_enh_top1,  4),
            "diff_top1_score":     round(avg_enh_top1 - avg_base_top1, 4),
            "improved_count":      improved,
            "total_count":         n,
        },
        "details": details,
    }

    out_path = Path(__file__).parent / "benchmark_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\n💾 결과 저장: {out_path}")
    print("   → 결과를 공유하면 README에 반영합니다.\n")


if __name__ == "__main__":
    main()
