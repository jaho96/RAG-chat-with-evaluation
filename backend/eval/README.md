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

## 평가 방식과 지표 기준

평가 스크립트는 `retrieval_eval.py`이며 LLM을 호출하지 않는다 (저장된 `rewritten_query`, `hyde`가 없으면 오류로 중단).

### 평가 프로토콜 (중요)

- 질문/방식(Vector-only, Hybrid)별로 **`search(top_k=10)`을 한 번만 실행**해 얻은 **하나의 Top-10 ranking**을 만든다.
- 이 ranking의 **앞 5개를 K=5, 앞 10개를 K=10 cutoff**로 평가한다. `search(top_k=5)`는 따로 실행하지 않는다.
- 두 방식은 같은 문서/청크, 같은 query embedding(저장된 HyDE를 동일한 임베딩 모델로 질문당 1회 임베딩), 같은 `top_k=10`으로 실행한다.

> **이 결과는 "서비스를 `top_k=5`로 실행했을 때의 결과"가 아니다.**
> "Top-10 retrieval ranking을 K=5와 K=10 cutoff에서 평가한 결과"이다.
>
> 이렇게 한 이유: 현재 Hybrid Search는 내부적으로 **`top_k × 3`개의 후보**를 Vector/Keyword 각각에서 가져와 RRF로 합산한다.
> 따라서 `top_k`를 바꾸면 **RRF 후보 집합 자체가 달라져서** Hybrid의 순위가 바뀔 수 있다
> (예: `top_k=5`의 결과가 `top_k=10` 결과의 앞 5개와 다른 경우가 실제로 있었다).
> 하나의 고정된 ranking을 cutoff로 평가하면 K를 바꿔도 같은 ranking을 비교하게 된다.
> (Vector-only는 후보 수가 달라도 순위가 같아 이 영향이 없다.)

### 지표

| 지표 | 기준 |
|---|---|
| Recall@K | `relevance=2` 청크만 relevant로 취급. (Top-K 안의 relevant 수) / (전체 relevant 수). K=5, 10 |
| MRR | 같은 Top-10 ranking에서 `relevance=2` 청크가 처음 등장한 순위의 역수 (Top-10 안에 없으면 0). 질문별 값은 RR, 질문 평균이 MRR |
| nDCG@K | `relevance` 0/1/2 graded relevance. **gain = relevance (linear)**, discount = 1/log2(rank+1). 정답 목록에 없는 청크는 0. IDCG는 정답 목록을 relevance 내림차순으로 K개까지 계산. K=5, 10 |

- exponential gain(`2^relevance - 1`)은 사용하지 않는다.
- 전체 결과는 질문별 지표의 **macro average**(질문 평균)로 요약한다.

### 해석 시 주의

- **질문이 5개뿐인 소규모 평가셋**이므로 결과를 통계적으로 일반화할 수 없다. 질문 하나가 평균을 크게 바꾼다.
- Vector 점수(cosine)와 Hybrid 점수(RRF)는 척도가 달라 서로 비교하지 않는다. 청크의 포함 여부와 순위만 사용한다.
- Recall@K는 정답(relevance=2) 개수에 영향을 받는다. 예를 들어 q004는 relevance=2가 8개라 K=5에서 Recall의 최댓값이 0.625이고, q005는 1개뿐이라 Recall이 0 또는 1로만 나온다.

## 재현성

- 평가 실행(`retrieval_compare.py`) 시 질문에 `rewritten_query`와 `hyde`가 저장되어 있으면 **LLM을 다시 호출하지 않고 저장된 값을 그대로 사용**한다.
- 둘 다 없으면 LLM으로 생성하고, 둘 중 하나만 있으면 오류로 처리한다.
- 일반 채팅(`chat.py`)의 동작은 이 설정과 무관하다.

## 실행

```bash
cd backend
source venv/bin/activate

# 검색 결과 나란히 보기 (지표 계산 없음)
python retrieval_compare.py --top-k 5

# Retrieval 평가 (Recall@5/10, MRR, nDCG@5/10; LLM 미호출)
python retrieval_eval.py
python retrieval_eval.py --ids q001 q004 --output eval/retrieval_eval_result.json
```
