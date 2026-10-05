"""
Retrieval 평가: Vector-only vs Hybrid(Vector + Keyword + RRF)

eval/questions.json 의 question / rewritten_query / hyde / relevant_chunks 를 사용한다.
- LLM을 호출하지 않는다 (저장된 rewritten_query, hyde 필수. 없으면 오류로 중단)
- HyDE 텍스트는 서비스와 동일한 임베딩 모델로 임베딩하며, 질문당 1회만 임베딩해 두 방식에 같은 벡터를 쓴다
- 같은 문서/청크에 대해 두 방식을 실행한다

평가 방식: 질문/방식별로 search(top_k=10)을 한 번만 실행해 얻은 하나의 Top-10 ranking 을
          cutoff K=5, K=10 에서 평가한다. (search(top_k=5)를 따로 실행하지 않는다)
  ※ 따라서 이 결과는 "서비스를 top_k=5로 실행했을 때의 결과"가 아니라
     "Top-10 ranking 을 K=5 / K=10 cutoff 에서 평가한 결과"이다.
     Hybrid 는 내부적으로 top_k×3 개 후보를 가져오므로 top_k 를 바꾸면 RRF 후보 집합이 달라진다.

지표 (relevant_chunks 의 relevance 기준 — eval/README.md 참고)
- Recall@K : relevance=2 인 청크만 relevant 로 취급. (Top-K 안의 relevant 수) / (전체 relevant 수)
- MRR      : 같은 Top-10 ranking 에서 relevance=2 청크가 처음 등장한 순위의 역수 (10위 안에 없으면 0).
             질문별 값은 RR, 질문 평균이 MRR
- nDCG@K   : relevance 0/1/2 graded relevance, gain = relevance (linear), discount = 1/log2(rank+1).
             정답 목록에 없는 청크는 relevance 0, IDCG 는 정답 목록을 relevance 내림차순으로 놓고 K 개까지 계산

주의: 질문이 5개뿐인 소규모 평가셋이므로 결과를 통계적으로 일반화할 수 없다.
      Vector 점수(cosine)와 Hybrid 점수(RRF)는 서로 비교하지 않고, 청크의 포함 여부와 순위만 사용한다.

사용법:
  cd backend
  source venv/bin/activate
  python retrieval_eval.py
  python retrieval_eval.py --ids q001 q004
  python retrieval_eval.py --output eval/retrieval_eval_result.json
"""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config  # noqa: F401 — .env 로드
from services.embedder import embed_query
from services.vector_store import search

DEFAULT_QUESTIONS = Path(__file__).parent / "eval" / "questions.json"
KS = (5, 10)          # 평가 cutoff
MAX_K = max(KS)       # 실제 검색은 top_k=MAX_K 로 한 번만 수행
MODES = ("vector", "hybrid")
MODE_LABEL = {"vector": "Vector-only", "hybrid": "Hybrid+RRF"}


# ── 지표 계산 (순수 함수) ───────────────────────────────────────────

def recall_at_k(ranked: list[str], qrels: dict[str, int], k: int) -> float:
    relevant = {c for c, r in qrels.items() if r == 2}
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def reciprocal_rank(ranked: list[str], qrels: dict[str, int]) -> float:
    for i, c in enumerate(ranked, 1):
        if qrels.get(c, 0) == 2:
            return 1.0 / i
    return 0.0


def dcg(rels: list[int]) -> float:
    """linear gain: gain = relevance"""
    return sum(r / math.log2(i + 2) for i, r in enumerate(rels))


def ndcg_at_k(ranked: list[str], qrels: dict[str, int], k: int) -> float:
    rels = [qrels.get(c, 0) for c in ranked[:k]]
    ideal = sorted(qrels.values(), reverse=True)[:k]
    idcg = dcg(ideal)
    return dcg(rels) / idcg if idcg > 0 else 0.0


def compute_metrics(ranked: list[str], qrels: dict[str, int]) -> dict:
    """ranked = search(top_k=10) 하나의 결과. 모든 지표를 이 ranking 의 cutoff 로 계산한다."""
    return {
        "recall@5": recall_at_k(ranked, qrels, 5),
        "recall@10": recall_at_k(ranked, qrels, 10),
        "rr": reciprocal_rank(ranked, qrels),
        "ndcg@5": ndcg_at_k(ranked, qrels, 5),
        "ndcg@10": ndcg_at_k(ranked, qrels, 10),
    }


# ── 검색 실행 ───────────────────────────────────────────────────────

def run_question(q: dict) -> dict[str, list[str]]:
    """질문 1개: 저장된 쿼리로 임베딩 1회 → 두 방식을 top_k=10 으로 한 번씩만 실행."""
    kw, hyde = (q.get("rewritten_query") or "").strip(), (q.get("hyde") or "").strip()
    if not kw or not hyde:
        raise ValueError(f"[{q['id']}] rewritten_query/hyde 가 저장되어 있지 않습니다. 평가에서는 LLM을 호출하지 않으므로 중단합니다.")

    embedding = embed_query(hyde)
    return {
        mode: [r["chunk_id"] for r in search(embedding, query_text=kw, top_k=MAX_K,
                                              mode=mode, include_chunk_id=True)]
        for mode in MODES
    }


# ── 출력 ────────────────────────────────────────────────────────────

def short(chunk_id: str) -> str:
    doc, idx = chunk_id.rsplit("_", 1)
    return f"{doc[:8]}_{idx}"


def fmt_rank(r: int | None) -> str:
    return f"{r}위" if r else "Top-10 밖"


def rank_of(lst: list[str], c: str) -> int | None:
    return lst.index(c) + 1 if c in lst else None


def print_question(q: dict, ranked: dict[str, list[str]], metrics: dict, qrels: dict[str, int], gt_meta: dict):
    n2 = sum(1 for r in qrels.values() if r == 2)
    n1 = sum(1 for r in qrels.values() if r == 1)
    print("=" * 100)
    print(f"[{q['id']}] {q['question']}   (정답: relevance=2 {n2}개, relevance=1 {n1}개)")
    print("-" * 100)
    print(f"  {'':<12}{'Recall@5':>10}{'Recall@10':>11}{'RR(MRR)':>10}{'nDCG@5':>9}{'nDCG@10':>10}")
    for mode in MODES:
        m = metrics[mode]
        print(f"  {MODE_LABEL[mode]:<12}{m['recall@5']:>10.3f}{m['recall@10']:>11.3f}{m['rr']:>10.3f}{m['ndcg@5']:>9.3f}{m['ndcg@10']:>10.3f}")

    print("\n  Top-10 ranking (괄호: 정답 relevance, ·=정답 목록에 없음)")
    for mode in MODES:
        items = " ".join(f"{short(c)}({qrels.get(c, '·')})" for c in ranked[mode])
        print(f"   {MODE_LABEL[mode]:<12}{items}")

    v10, h10 = ranked["vector"], ranked["hybrid"]
    print("\n  정답 청크 순위 (같은 Top-10 ranking 기준)")
    print(f"   {'chunk':<14}{'rel':>4}  {'Vector':<10}{'Hybrid':<10}변화")
    order = sorted(qrels, key=lambda c: (-qrels[c], gt_meta[c]["filename"], gt_meta[c]["chunk_index"]))
    for c in order:
        vr, hr = rank_of(v10, c), rank_of(h10, c)
        if vr and hr:
            change = f"개선 ({vr}→{hr}위)" if hr < vr else (f"하락 ({vr}→{hr}위)" if hr > vr else "동일")
        elif hr and not vr:
            change = "Hybrid에서만 진입"
        elif vr and not hr:
            change = "Hybrid에서 밀려남"
        else:
            change = "둘 다 Top-10 밖"
        print(f"   {short(c):<14}{qrels[c]:>4}  {fmt_rank(vr):<10}{fmt_rank(hr):<10}{change}")

    print("\n  Top-K 멤버십 변화 (Vector 대비 Hybrid, 같은 ranking 의 앞 K개)")
    for k in KS:
        vset, hset = set(v10[:k]), set(h10[:k])
        for label, want in (("relevance=2", 2), ("relevance=1", 1)):
            entered = [short(c) for c in order if qrels[c] == want and c in hset and c not in vset]
            dropped = [short(c) for c in order if qrels[c] == want and c in vset and c not in hset]
            print(f"   K={k:<2} {label}: Hybrid에서 새로 진입 {entered or '-'} / Hybrid 때문에 Top-{k} 밖으로 밀림 {dropped or '-'}")
    print()


def print_macro(avg: dict, n: int):
    print("=" * 100)
    print(f"전체 평균 (macro average, 질문 {n}개 — 소규모 평가셋이므로 통계적으로 일반화할 수 없음)")
    print("-" * 100)
    print(f"  {'':<12}{'Recall@5':>10}{'Recall@10':>11}{'MRR':>10}{'nDCG@5':>9}{'nDCG@10':>10}")
    for mode in MODES:
        m = avg[mode]
        print(f"  {MODE_LABEL[mode]:<12}{m['recall@5']:>10.3f}{m['recall@10']:>11.3f}{m['rr']:>10.3f}{m['ndcg@5']:>9.3f}{m['ndcg@10']:>10.3f}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Vector-only vs Hybrid Retrieval 평가 (LLM 미호출)")
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS, help="질문/정답 JSON")
    parser.add_argument("--ids", nargs="*", help="이 id의 질문만 평가 (생략 시 전체)")
    parser.add_argument("--output", type=Path, help="상세 결과를 JSON으로 저장할 경로 (선택)")
    args = parser.parse_args()

    questions = json.loads(args.questions.read_text(encoding="utf-8"))
    if args.ids:
        questions = [q for q in questions if q["id"] in set(args.ids)]
    if not questions:
        print("평가할 질문이 없습니다.")
        return

    print(f"Retrieval 평가 | 질문 {len(questions)}개 | 방식별 search(top_k={MAX_K}) 1회 → cutoff K={list(KS)} | nDCG gain=linear | LLM 호출 없음")
    print("※ 이 결과는 '서비스를 top_k=5로 실행한 결과'가 아니라 'Top-10 ranking 을 K=5/K=10 cutoff 에서 평가한 결과'입니다.")
    print("※ 소규모 평가셋입니다. 결과를 통계적으로 일반화하지 마세요. Vector 점수(cosine)와 RRF 점수는 비교하지 않습니다.\n")

    results, per_q = [], {m: [] for m in MODES}
    for q in questions:
        qrels = {c["chunk_id"]: c["relevance"] for c in q["relevant_chunks"]}
        gt_meta = {c["chunk_id"]: c for c in q["relevant_chunks"]}
        ranked = run_question(q)
        metrics = {m: compute_metrics(ranked[m], qrels) for m in MODES}
        for m in MODES:
            per_q[m].append(metrics[m])
        print_question(q, ranked, metrics, qrels, gt_meta)
        results.append({"id": q["id"], "question": q["question"], "ranking_top10": ranked, "metrics": metrics})

    avg = {m: {k: sum(x[k] for x in per_q[m]) / len(per_q[m]) for k in per_q[m][0]} for m in MODES}
    print_macro(avg, len(questions))

    if args.output:
        args.output.write_text(
            json.dumps({"protocol": "search(top_k=10) once per question/mode; metrics at cutoff K=5,10 of the same ranking",
                        "cutoffs": list(KS), "gain": "linear", "n_questions": len(questions),
                        "macro_average": avg, "questions": results}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"결과 저장: {args.output}")


if __name__ == "__main__":
    main()
