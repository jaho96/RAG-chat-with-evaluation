"""
검색 방식 비교: Vector-only vs Hybrid(Vector + Keyword + RRF)

같은 질문에 대해 prepare_queries()와 임베딩을 한 번만 수행하고,
완전히 동일한 query embedding / top_k 로 두 방식을 실행해 청크 ID와 순위를 나란히 출력한다.
(Recall@K, MRR, nDCG 계산은 아직 포함하지 않음)

사용법:
  cd backend
  source venv/bin/activate
  python retrieval_compare.py
  python retrieval_compare.py --top-k 5 --ids q001 q003
  python retrieval_compare.py --questions eval/questions.json --output eval/compare_result.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: F401 — .env 로드
from services.embedder import embed_query
from services.query_rewriter import prepare_queries
from services.vector_store import search

DEFAULT_QUESTIONS = Path(__file__).parent / "eval" / "questions.json"


def load_questions(path: Path, ids: list[str] | None) -> list[dict]:
    questions = json.loads(path.read_text(encoding="utf-8"))
    if ids:
        questions = [q for q in questions if q["id"] in set(ids)]
    return questions


def compare_one(question: str, top_k: int, provider: str, model: str) -> dict:
    """질문 1개에 대해 query 준비·임베딩은 1회만 수행하고, 두 방식을 같은 입력으로 검색한다."""
    keyword_query, hyde_text = prepare_queries(question, provider, model)
    embedding = embed_query(hyde_text)

    vector = search(embedding, query_text=keyword_query, top_k=top_k,
                    mode="vector", include_chunk_id=True)
    hybrid = search(embedding, query_text=keyword_query, top_k=top_k,
                    mode="hybrid", include_chunk_id=True)

    def pack(results: list[dict]) -> list[dict]:
        return [{"rank": i, "chunk_id": r["chunk_id"], "score": r["score"]}
                for i, r in enumerate(results, 1)]

    return {
        "keyword_query": keyword_query,
        "hyde_text": hyde_text,
        "vector": pack(vector),
        "hybrid": pack(hybrid),
    }


def print_comparison(q: dict, r: dict, top_k: int):
    vec_ids = {x["chunk_id"] for x in r["vector"]}
    hyb_ids = {x["chunk_id"] for x in r["hybrid"]}

    print("=" * 100)
    print(f"[{q['id']}] {q['question']}")
    print(f"  keyword_query : {r['keyword_query']}")
    print(f"  hyde_text     : {r['hyde_text'][:80]}{'…' if len(r['hyde_text']) > 80 else ''}")
    print(f"  (* = 반대편 Top-{top_k}에도 포함된 청크)")
    print("-" * 100)
    print(f"  {'rank':<5} {'Vector-only (cosine)':<46} {'Hybrid + RRF (정규화 RRF)':<46}")
    for i in range(top_k):
        v = r["vector"][i] if i < len(r["vector"]) else None
        h = r["hybrid"][i] if i < len(r["hybrid"]) else None

        def cell(x, other_ids):
            if not x:
                return "-"
            mark = "*" if x["chunk_id"] in other_ids else " "
            return f"{mark}{x['chunk_id']} ({x['score']:.3f})"

        print(f"  {i + 1:<5} {cell(v, hyb_ids):<46} {cell(h, vec_ids):<46}")
    print(f"  공통 청크 {len(vec_ids & hyb_ids)}개 / Vector 전용 {len(vec_ids - hyb_ids)}개"
          f" / Hybrid 전용 {len(hyb_ids - vec_ids)}개")


def main():
    parser = argparse.ArgumentParser(description="Vector-only vs Hybrid 검색 결과 비교")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS, help="질문 JSON 파일")
    parser.add_argument("--ids", nargs="*", help="이 id의 질문만 실행 (생략 시 전체)")
    parser.add_argument("--top-k", type=int, default=7, help="검색 결과 수 (서비스 기본값: 7)")
    parser.add_argument("--provider", default="gemini", help="쿼리 재작성·HyDE에 쓸 LLM 제공사")
    parser.add_argument("--model", default="gemini-2.5-flash", help="쿼리 재작성·HyDE에 쓸 LLM 모델")
    parser.add_argument("--output", type=Path, help="결과를 JSON으로 저장할 경로 (선택)")
    args = parser.parse_args()

    questions = load_questions(args.questions, args.ids)
    if not questions:
        print("실행할 질문이 없습니다.")
        return

    print(f"질문 {len(questions)}개 | top_k={args.top_k} | 쿼리 LLM: {args.provider}/{args.model}")

    results = []
    for q in questions:
        try:
            r = compare_one(q["question"], args.top_k, args.provider, args.model)
        except Exception as e:
            print(f"[{q['id']}] 실패: {e}")
            continue
        print_comparison(q, r, args.top_k)
        results.append({"id": q["id"], "question": q["question"], "top_k": args.top_k, **r})

    if args.output:
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n결과 저장: {args.output}")


if __name__ == "__main__":
    main()
