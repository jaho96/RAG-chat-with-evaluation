"""
벡터 저장소 — PostgreSQL + pgvector
"""

import numpy as np
import psycopg2.extras
from services.db import get_conn

_STOP_WORDS = {
    "알려줘", "알려주세요", "설명해줘", "설명해주세요", "얘기해줘", "말해줘",
    "대해", "관해", "관련해서", "에서", "에서는", "에서의",
    "무엇", "뭐야", "뭐", "어떤", "어떻게", "왜", "언제", "어디",
    "이야", "인가", "인지", "인데", "이란", "이라는", "이고", "이에요",
    "해줘", "해주세요", "해봐", "해봐줘",
    "좀", "조금", "간단히", "자세히", "쉽게", "간략히",
    "알고", "싶어", "싶은데", "궁금해", "궁금한데", "궁금합니다",
    "있나요", "있어", "있어요", "있을까", "될까", "될까요",
    "이", "가", "을", "를", "의", "에", "와", "과", "로", "으로",
}


def _build_keyword_query(text: str) -> str:
    words = [w for w in text.strip().split() if w not in _STOP_WORDS and len(w) > 1]
    return " | ".join(words) if words else ""


def add_chunks(doc_id: str, filename: str, file_type: str, uploaded_at: str,
               file_size: int, file_hash: str, chunks: list[dict],
               embeddings: list[list[float]], total_chunks: int):
    with get_conn() as conn:
        cur = conn.cursor()

        # 문서 메타데이터 저장
        cur.execute("""
            INSERT INTO documents
              (doc_id, filename, file_type, uploaded_at, file_size, file_hash, total_chunks)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (doc_id) DO NOTHING
        """, (doc_id, filename, file_type, uploaded_at, file_size, file_hash, total_chunks))

        # 청크 + 임베딩 배치 INSERT (개별 INSERT 대비 대폭 빠름)
        rows = [
            (
                f"{doc_id}_{chunk['chunk_index']}",
                doc_id, filename, file_type, uploaded_at,
                chunk.get("page") if chunk.get("page") is not None else -1,
                chunk["chunk_index"], len(chunk["text"]),
                total_chunks, chunk["text"],
                np.array(embedding, dtype=np.float32),
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO document_chunks
              (chunk_id, doc_id, filename, file_type, uploaded_at,
               page, chunk_index, chunk_size, total_chunks, content, embedding)
            VALUES %s
            ON CONFLICT (chunk_id) DO NOTHING
            """,
            rows,
            page_size=100,
        )


def _format_result(row: dict, score: float, include_chunk_id: bool) -> dict:
    """검색 결과 1건을 응답 형식으로 변환. chunk_id는 평가용 옵션으로만 포함한다."""
    item = {
        "text": row["content"],
        "metadata": {
            "doc_id":       row["doc_id"],
            "filename":     row["filename"],
            "file_type":    row["file_type"],
            "uploaded_at":  row["uploaded_at"],
            "page":         row["page"],
            "chunk_index":  row["chunk_index"],
            "total_chunks": row["total_chunks"],
        },
        "score": score,
    }
    if include_chunk_id:
        item["chunk_id"] = row["chunk_id"]
    return item


def search(query_embedding: list[float], query_text: str = "", top_k: int = 5,
           mode: str = "hybrid", include_chunk_id: bool = False) -> list[dict]:
    """
    문서 검색.

    mode="hybrid" (기본): 벡터 유사도 + 키워드 검색 결합 (RRF 방식)
    mode="vector"       : 벡터 검색만 수행, 코사인 유사도 순으로 top_k 반환 (평가용)

    include_chunk_id=True 이면 각 결과에 "chunk_id"를 추가한다 (평가용, 기본 응답에는 영향 없음).
    """
    if mode not in ("hybrid", "vector"):
        raise ValueError(f"지원하지 않는 검색 mode: {mode!r} (hybrid | vector)")

    vec = np.array(query_embedding, dtype=np.float32)
    fetch = top_k * 3  # 각 방법에서 더 많이 뽑아서 합산

    with get_conn() as conn:
        cur = conn.cursor()

        # ── 벡터 검색 ──────────────────────────────────────────────
        cur.execute("""
            SELECT chunk_id, doc_id, filename, file_type, uploaded_at,
                   page, chunk_index, total_chunks, content,
                   1 - (embedding <=> %s) AS score
            FROM document_chunks
            ORDER BY embedding <=> %s
            LIMIT %s
        """, (vec, vec, fetch))
        vector_rows = {r["chunk_id"]: (dict(r), i + 1) for i, r in enumerate(cur.fetchall())}

        # ── 키워드 검색 (tsvector) ─────────────────────────────────
        keyword_rows = {}
        words = _build_keyword_query(query_text) if mode == "hybrid" and query_text.strip() else ""
        if words:
            try:
                cur.execute("""
                    SELECT chunk_id, doc_id, filename, file_type, uploaded_at,
                           page, chunk_index, total_chunks, content,
                           ts_rank(content_tsv, to_tsquery('simple', %s)) AS score
                    FROM document_chunks
                    WHERE content_tsv @@ to_tsquery('simple', %s)
                    ORDER BY score DESC
                    LIMIT %s
                """, (words, words, fetch))

                keyword_rows = {r["chunk_id"]: (dict(r), i + 1) for i, r in enumerate(cur.fetchall())}
            except Exception:
                pass  # 키워드 파싱 실패 시 벡터만 사용

    # ── Vector-only: 코사인 유사도 순(이미 정렬됨)으로 top_k 반환 ──
    if mode == "vector":
        ranked = sorted(vector_rows.values(), key=lambda x: x[1])
        return [_format_result(r, round(r["score"], 3), include_chunk_id) for r, _ in ranked[:top_k]]

    # ── RRF (Reciprocal Rank Fusion) 점수 합산 ─────────────────────
    k = 60  # RRF 상수
    max_rrf = 2 / (k + 1)  # 양쪽 모두 1위일 때 최댓값
    all_ids = set(vector_rows) | set(keyword_rows)
    scored = []
    for cid in all_ids:
        rrf = 0.0
        row_data = None
        if cid in vector_rows:
            row_data, rank = vector_rows[cid]
            rrf += 1 / (k + rank)
        if cid in keyword_rows:
            row_data, rank = keyword_rows[cid]
            rrf += 1 / (k + rank)
        if row_data:
            scored.append((rrf, row_data))

    scored.sort(key=lambda x: x[0], reverse=True)

    # RRF 점수를 0~1로 정규화 — 벡터+키워드 양쪽 1위면 1.0
    return [
        _format_result(r, round(min(rrf / max_rrf, 1.0), 3), include_chunk_id)
        for rrf, r in scored[:top_k]
    ]


def get_document_by_hash(file_hash: str) -> dict | None:
    """중복 파일 확인"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT doc_id, filename FROM documents WHERE file_hash = %s",
            (file_hash,)
        )
        row = cur.fetchone()
    return dict(row) if row else None


def delete_document(doc_id: str):
    """문서 삭제 — ON DELETE CASCADE 로 청크도 자동 삭제"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))


def list_documents() -> list[dict]:
    """문서 목록 (최신순)"""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM documents ORDER BY uploaded_at DESC")
        return [dict(r) for r in cur.fetchall()]


def get_chunks_text(doc_ids: list[str]) -> list[str]:
    """퀴즈 생성용 — 특정 문서들의 청크 텍스트만 반환"""
    with get_conn() as conn:
        cur = conn.cursor()
        if doc_ids:
            cur.execute(
                "SELECT content FROM document_chunks WHERE doc_id = ANY(%s)",
                (doc_ids,)
            )
        else:
            cur.execute("SELECT content FROM document_chunks")
        return [r["content"] for r in cur.fetchall()]