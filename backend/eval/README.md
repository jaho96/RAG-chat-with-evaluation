# Retrieval 평가 데이터셋

`questions.json` — Vector-only vs Hybrid(Vector + Keyword + RRF) 검색 비교 평가용 질문과 정답(Ground Truth).

## 스키마

| 필드 | 설명 |
|---|---|
| `id` | 질문 ID (`q001` …) |
| `question` | 질문 원문 |
| `category` | 질문 유형: `concept`(개념 설명), `method`(방법), `design`(설계), `usage`(사용법) |
| `rewritten_query` | 저장된 Query Rewriting 결과 (키워드 검색용) |
| `hyde` | 저장된 HyDE 가상 답변 (벡터 검색용, 임베딩은 저장하지 않고 실행 시 같은 모델로 임베딩) |
| `query_generation` | `rewritten_query`/`hyde`를 만든 LLM(`provider`, `model`)과 생성일(`generated_at`) |
| `relevant_chunks` | 정답 청크 목록 (아래 참고) |

`relevant_chunks` 항목:

| 필드 | 설명 |
|---|---|
| `chunk_id` | DB `document_chunks.chunk_id` (`문서UUID_청크번호`) |
| `relevance` | 관련도 등급 (1 또는 2). 0은 목록에 넣지 않음 |
| `filename`, `page`, `chunk_index` | 사람이 확인하고, 문서를 다시 올려 `chunk_id`가 바뀌었을 때 재매핑하기 위한 정보 |
| `note` | 해당 등급으로 판단한 이유 |

> `chunk_id`의 문서 UUID는 문서를 삭제 후 재업로드하면 바뀝니다. 그 경우 `filename` + `chunk_index`로 다시 매핑해야 합니다.

## 관련도(relevance) 기준

| 값 | 의미 |
|---|---|
| 2 | 해당 청크 자체만으로 질문에 직접 답할 수 있는 청크 |
| 1 | 질문과 관련은 있지만 단독으로 충분한 답변을 만들기 어려운 보조 청크 |
| 0 | 용어나 주변 내용만 언급되어 실질적인 답변 근거로 보기 어려운 청크 (데이터에는 기록하지 않음) |

**청크 오버랩 규칙**: 청크가 200자씩 겹쳐서 같은 핵심 내용이 인접한 두 청크에 들어 있고, 둘 중 어느 청크를 검색해도 답변 생성에 충분하면 둘 다 `relevance=2`로 인정한다.

**제외 규칙**: 질문 주제의 명령어·용어가 한두 줄만 언급되고 실제 사용법·설명이 없는 청크는 정답에 넣지 않는다 (예: q004의 `/model` 출력 예, `/plan` 한 줄 언급).

## 평가 지표 기준 (추후 계산)

| 지표 | 기준 |
|---|---|
| Recall@K | `relevance=2` 청크를 relevant로 취급 |
| MRR | `relevance=2`인 첫 번째 청크의 순위 기준 |
| nDCG@K | `relevance` 0/1/2의 graded relevance 사용 (목록에 없는 청크는 0) |

## 재현성

- 평가 실행(`retrieval_compare.py`) 시 질문에 `rewritten_query`와 `hyde`가 저장되어 있으면 **LLM을 다시 호출하지 않고 저장된 값을 그대로 사용**한다.
- 둘 다 없으면 LLM으로 생성하고, 둘 중 하나만 있으면 오류로 처리한다.
- 일반 채팅(`chat.py`)의 동작은 이 설정과 무관하다.

## 실행

```bash
cd backend
source venv/bin/activate
python retrieval_compare.py --top-k 5
python retrieval_compare.py --top-k 5 --ids q001 q004 --output eval/compare_result.json
```
