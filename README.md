# RAG Chat

> 문서를 업로드하고 AI와 대화할 수 있는 RAG(Retrieval-Augmented Generation) 기반 챗봇 시스템

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL+pgvector-16-4169E1?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-required-2496ED?logo=docker&logoColor=white)

---

## 📌 주요 기능

### 📄 문서 관리
- **다중 업로드** — PDF, DOCX, TXT, HWP 파일을 한 번에 여러 개 드래그·선택 업로드
- **업로드 큐** — 임베딩 처리 중에도 새 파일을 추가할 수 있으며, 순서대로 자동 처리 (대기·처리중·완료·실패 상태 표시)
- **파일 타입별 그룹화** — 사이드바에서 파일 유형별 폴더 구조로 표시
- **개별·전체 삭제** — 문서 단위 삭제 및 전체 초기화 지원
- **중복 방지** — 파일 해시 기반으로 동일 파일 재업로드 차단

### 💬 RAG 채팅
- **스트리밍 응답** — LLM 답변을 토큰 단위로 실시간 출력
- **마크다운 렌더링** — 소제목, 목록, 표, 코드 블록 등 구조화된 답변을 마크다운으로 표시
- **검색 상태 표시** — HyDE 및 벡터 검색 중 "문서를 검색하고 있습니다…" 실시간 표시
- **참고 출처 표시** — 답변에 사용된 청크 파일명·페이지·관련도 점수 표시
- **메타 쿼리 처리** — "어떤 문서가 있나요?", "요약해줘" 등 문서 관련 질문 자동 처리
- **대화 히스토리** — 대화 저장·불러오기, 참고 출처 복원, 새 채팅·전체 삭제
- **대화 맥락 관리** — 토큰 기반 히스토리 트리밍으로 긴 대화도 맥락 유지
- **응답 캐시** — Redis를 통한 동일 질문 즉시 응답
- **응답 피드백** — 답변에 👍 / 👎 평가
- **예시 질문 카드** — 첫 질문을 돕는 클릭 가능한 예시 카드

### 🔍 검색 품질
- **하이브리드 검색** — 벡터 유사도 검색 + 키워드 검색(tsvector)을 RRF로 결합
- **쿼리 재작성(Query Rewriting)** — "~에 대해 알려줘" 같은 대화체를 핵심 키워드로 변환하여 키워드 검색 정확도 향상
- **HyDE(Hypothetical Document Embedding)** — 질문에 대한 가상 답변 단락을 생성해 임베딩, 문서와 유사한 문체·어휘로 코사인 유사도 향상
- **병렬 실행** — 쿼리 재작성과 HyDE를 동시에 실행해 응답 지연 최소화
- **RRF 정규화 점수** — 검색 관련도를 RRF 순위 기반으로 0~100%로 정규화 (벡터·키워드 양쪽 1위 = 100%)

### 📊 평가 & 모니터링
- **자체 평가 대시보드** (3탭)
  - **응답 품질** : 응답시간·검색 관련도·가독성 점수 추이 차트, 만족도·캐시 히트율 통계
  - **임베딩 품질** : 문서별 청크 크기 분포, 짧은 청크 비율 (문서 유형별 권장 범위 안내)
  - **업로드 성능** : 파싱·청킹·임베딩·DB 저장 단계별 소요 시간, 가로형 스택 바 차트 + 호버 시 총계 표시
- **LLM-as-judge 가독성 평가** — 답변 완료 후 백그라운드에서 LLM이 가독성을 1~5점으로 자동 평가, 대시보드에서 추이 확인
- **RAG 디버깅** — Arize Phoenix를 통한 파이프라인 스팬 추적
- **LangSmith 연동** — 트레이스 저장 및 품질 분석

### 🎯 기타
- **다중 LLM 지원** — 아래 표 참고
- **서버 상태 표시** — 사이드바에서 백엔드 연결 상태 실시간 확인 (10초마다 갱신)
- **퀴즈 생성** — 업로드된 문서 내용으로 단답형·객관식 퀴즈 자동 생성

---

## 🤖 지원 LLM 모델

| 제공사 | 모델 | 무료 여부 |
|--------|------|:---------:|
| Google Gemini | Gemini 2.5 Flash / 2.5 Flash-Lite / 3.5 Flash / 3.8 Flash | ✅ 무료 |
| Groq | GPT-OSS 120B / GPT-OSS 20B / Qwen3.8 27B | ✅ 무료 |
| OpenAI | GPT-4o | 💳 유료 (UI 숨김) |
| OpenAI | GPT-4o Mini | 💳 유료 (UI 숨김) |
| Anthropic | Claude Sonnet 4.6 | 💳 유료 (UI 숨김) |
| Anthropic | Claude Haiku 4.5 | 💳 유료 (UI 숨김) |

---

## 🏗️ RAG 파이프라인

```
사용자 질문 입력
       │
       ├─────────────────────────────────────────────┐
       │ [병렬 실행]                                  │
       ▼                                             ▼
쿼리 재작성 (LLM)                           HyDE 생성 (LLM)
"머신러닝 개념 원리"                  "머신러닝은 데이터로부터..."
       │                                             │
       ▼                                             ▼
  키워드 검색 (tsvector)               임베딩 → 벡터 검색 (pgvector)
       │                                             │
       └──────────────── RRF 점수 합산 ──────────────┘
                                │
                           상위 K개 청크
                                │
                    시스템 프롬프트 + 맥락 구성
                                │
                          LLM 스트리밍 답변
                                │
                    트레이스 저장 / 캐시 저장
```

---

## 🔬 검색 성능 벤치마크

동일한 질문 5개를 **기본 검색**과 **향상 검색**으로 각각 실행해 비교한 실측값입니다.

| 방식 | 설명 |
|------|------|
| 기본 검색 | 질문 원문 → 임베딩 → 벡터 검색 |
| 향상 검색 | 쿼리 재작성 + HyDE 병렬 생성 → 임베딩 → 벡터 + 키워드 하이브리드 검색 (RRF) |

### 결과 (문서 187청크, top_k=7, Groq Llama 3.3 70B — 측정 당시 모델)

| 지표 | 기본 검색 | 향상 검색 | 개선폭 |
|------|:---------:|:---------:|:------:|
| 평균 관련도 (avg) | 47.7% | 87.3% | **+39.6%p** |
| Top-1 관련도 | 50.0% | 98.9% | **+48.9%p** |
| 향상된 질문 비율 | — | — | **5 / 5 (100%)** |

### 질문별 상세

| 질문 | 기본 avg | 향상 avg | 개선폭 |
|------|:--------:|:--------:|:------:|
| 딥러닝과 언어 모델링에 대해 알려줘 | 47.7% | 84.6% | +36.9%p |
| 깃헙에서 URL로 열기 방법은 뭐야? | 47.7% | 90.8% | +43.1%p |
| 구글 코랩에서 노트 열기 설정은 어떻게 해? | 47.7% | 89.2% | +41.5%p |
| 트랜스포머 아키텍처는 언제 발표된 거야? | 47.7% | 80.0% | +32.3%p |
| Language Model이란게 정확히 무엇이야? | 47.7% | 91.8% | +44.1%p |

> 관련도 점수는 RRF 정규화 기준 (벡터·키워드 양쪽 1위 = 100%).
> 벤치마크 재현: `cd backend && python benchmark.py`

---

## 🛠️ 기술 스택

### Backend
| 항목 | 내용 |
|------|------|
| 프레임워크 | FastAPI |
| 벡터 DB | PostgreSQL + pgvector |
| 연결 관리 | psycopg2 ThreadedConnectionPool |
| 임베딩 | OpenAI text-embedding-3-small (1536차원) |
| 청킹 | 900자 / 오버랩 200자 (한국어 기술 문서 최적화) |
| LLM | Groq / Google Gemini / OpenAI / Anthropic Claude |
| 캐시 | Redis (선택) |
| 문서 파싱 | PyMuPDF, python-docx, olefile |
| 모니터링 | LangSmith, Arize Phoenix |

### Frontend
| 항목 | 내용 |
|------|------|
| 프레임워크 | React 18 + TypeScript |
| 번들러 | Vite |
| 스타일 | Tailwind CSS |
| 차트 | Recharts |
| 마크다운 | react-markdown + remark-gfm |

---

## 🚀 시작하기

### 사전 요구사항

| 항목 | 버전 | 필수 여부 |
|------|------|:---------:|
| Python | 3.11+ | ✅ 필수 |
| Node.js | 18+ | ✅ 필수 |
| Docker Desktop | 최신 | ✅ 필수 |
| WSL2 | - | ✅ 필수 (Windows) |
| Redis | - | 선택 |

### 1. PostgreSQL + pgvector 컨테이너 시작

최초 실행:
```bash
docker run -d --name pgvector \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=ragdb \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

이후 실행 시:
```bash
docker start pgvector
```

### 2. Redis 설치 (WSL, 선택)

```bash
sudo apt-get install -y redis-server
sudo service redis-server start
```

### 3. 백엔드 설정

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`.env` 파일 생성:

```env
# 필수 (사용할 LLM에 해당하는 키만 있어도 됨)
OPENAI_API_KEY=your_openai_key
GROQ_API_KEY=your_groq_key
GOOGLE_API_KEY=your_google_key
ANTHROPIC_API_KEY=your_anthropic_key

# 필수
DATABASE_URL=postgresql://postgres:password@localhost:5432/ragdb

# 선택
REDIS_URL=redis://localhost:6379
LANGSMITH_API_KEY=your_langsmith_key
LANGSMITH_PROJECT=rag-project
PHOENIX_PROJECT=rag-chat
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
```

백엔드 실행:
```bash
fuser -k 8000/tcp; uvicorn main:app --reload
```

### 4. Arize Phoenix 실행 (선택, 별도 터미널)

```bash
source venv/bin/activate
python -m phoenix.server.main serve
```

Phoenix UI: `http://localhost:6006`

### 5. 프론트엔드 설정

```bash
cd frontend
npm install
fuser -k 5173/tcp; npm run dev
```

브라우저에서 `http://localhost:5173` 접속

> **WSL 환경:** Vite가 출력하는 Network URL(`172.x.x.x:5173`) 사용

> ⚠️ **주의:** 서버 종료 시 반드시 **Ctrl+C** 사용. Ctrl+Z는 프로세스를 백그라운드로 보내 포트를 계속 점유한다.

---

## 📁 프로젝트 구조

```
RAG_Project/
├── backend/
│   ├── main.py                    # FastAPI 앱 진입점, 라이프사이클 관리
│   ├── config.py                  # 환경변수 설정
│   ├── requirements.txt
│   ├── routers/
│   │   ├── chat.py                # 채팅 스트리밍, 메타 쿼리, 피드백
│   │   ├── documents.py           # 문서 업로드·삭제(개별·전체), 업로드 성능 기록
│   │   ├── conversations.py       # 대화 히스토리 CRUD
│   │   ├── evaluate.py            # 응답 품질·임베딩 품질·업로드 성능 통계 API
│   │   └── quiz.py                # 퀴즈 생성·채점
│   └── services/
│       ├── db.py                  # PostgreSQL 연결 풀, 테이블 초기화
│       ├── vector_store.py        # pgvector 청크 저장·하이브리드 검색(RRF, 불용어 필터)
│       ├── query_rewriter.py      # 쿼리 재작성 + HyDE 병렬 실행
│       ├── embedder.py            # OpenAI 임베딩 (캐시 연동)
│       ├── document_parser.py     # PDF·DOCX·TXT·HWP 파싱 및 청킹
│       ├── conversation_store.py  # 대화·메시지 저장소 (sources 포함)
│       ├── trace_store.py         # 트레이스 저장소
│       ├── history_manager.py     # 대화 히스토리 토큰 관리·요약
│       ├── cache.py               # Redis 캐시 (임베딩·응답)
│       ├── readability_evaluator.py  # LLM-as-judge 가독성 자동 평가 (백그라운드 스레드)
│       ├── phoenix_tracer.py      # Arize Phoenix OpenTelemetry 계측
│       ├── langsmith_tracer.py    # LangSmith 연동
│       └── llm/
│           ├── __init__.py        # LLM 팩토리 (get_llm)
│           ├── base.py            # BaseLLM 인터페이스
│           ├── openai_llm.py      # OpenAI GPT-4o
│           ├── groq_llm.py        # Groq Llama
│           ├── claude_llm.py      # Anthropic Claude
│           └── gemini_llm.py      # Google Gemini
└── frontend/
    ├── src/
    │   ├── pages/
    │   │   ├── ChatPage.tsx       # 채팅 페이지, 예시 질문 카드
    │   │   ├── EvaluatePage.tsx   # 평가 페이지 (응답 품질·임베딩 품질·업로드 성능 탭)
    │   │   └── QuizPage.tsx       # 퀴즈 페이지
    │   ├── components/
    │   │   ├── Layout.tsx         # 사이드바, 네비게이션, 서버 상태 표시
    │   │   ├── ChatWindow.tsx     # 메시지 목록, 피드백 버튼
    │   │   ├── FileUpload.tsx     # 문서 업로드 (드래그·다중 선택·진행 표시)
    │   │   ├── ModelSelector.tsx  # LLM 모델 선택 (Portal 드롭다운)
    │   │   ├── SourceViewer.tsx   # 참고 출처 표시
    │   │   └── evaluate/
    │   │       ├── DashboardTab.tsx   # 응답 품질 대시보드 (초기화 포함)
    │   │       ├── EmbeddingTab.tsx   # 임베딩 품질 분석
    │   │       └── UploadTab.tsx      # 업로드 성능 분석 (초기화 포함)
    │   └── types/index.ts         # 공통 타입 정의
    └── vite.config.ts             # Vite 설정 (프록시, strictPort)
```

---

## 🔌 API 엔드포인트

### 문서
| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/documents/upload` | 문서 업로드 (성능 자동 기록) |
| `GET` | `/documents/` | 문서 목록 |
| `DELETE` | `/documents/` | 문서 전체 삭제 |
| `DELETE` | `/documents/{id}` | 문서 개별 삭제 |

### 채팅
| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/chat/models` | 사용 가능한 모델 목록 |
| `POST` | `/chat/stream` | RAG 채팅 (SSE 스트리밍) |
| `POST` | `/chat/feedback` | 답변 피드백 (👍 / 👎) |

### 대화 히스토리
| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/conversations/` | 대화 목록 |
| `POST` | `/conversations/` | 대화 생성 |
| `GET` | `/conversations/{id}/messages` | 메시지 불러오기 |
| `POST` | `/conversations/{id}/messages` | 메시지 저장 |
| `DELETE` | `/conversations/{id}` | 대화 삭제 |

### 평가
| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/evaluate/stats` | 응답 품질 통계 |
| `GET` | `/evaluate/traces` | 트레이스 목록 |
| `DELETE` | `/evaluate/traces` | 트레이스 전체 삭제 |
| `GET` | `/evaluate/embedding-stats` | 임베딩 품질 통계 |
| `GET` | `/evaluate/upload-traces` | 업로드 성능 기록 |
| `DELETE` | `/evaluate/upload-traces` | 업로드 성능 기록 전체 삭제 |

### 기타
| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/health` | 서버 상태 확인 |
| `POST` | `/quiz/generate` | 퀴즈 생성 |
| `POST` | `/quiz/grade` | 퀴즈 채점 |

---

## ▶️ 서버 시작 방법 (요약)

```bash
# 1. PostgreSQL 컨테이너
docker start pgvector

# 2. 백엔드 (WSL 터미널 1)
cd "/mnt/c/Users/.../backend"
source venv/bin/activate
fuser -k 8000/tcp; uvicorn main:app --reload

# 3. Phoenix (WSL 터미널 2, 선택)
source venv/bin/activate
python -m phoenix.server.main serve

# 4. 프론트엔드 (WSL 터미널 3)
cd "/mnt/c/Users/.../frontend"
fuser -k 5173/tcp; npm run dev
```
