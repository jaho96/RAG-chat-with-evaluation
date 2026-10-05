# CLAUDE.md — RAG Chat 프로젝트 작업 인계 노트

> 이 파일은 `main`용 축약본이다. 진행 중인 Retrieval 평가 작업의 상세 내용은 `retrieval-evaluation` 브랜치의 CLAUDE.md(6장)에 있다.

새 세션에서 이전 작업을 이어가기 위한 메모. 코드 구조·기능 설명은 `README.md`에 있으니 여기서는 **환경 함정, 현재 상태, 합의된 작업 방식**만 적는다.
(기록 시점: 2026-10-05. 모델 목록·무료 한도·커밋 해시는 바뀔 수 있으니 필요하면 다시 확인할 것.)

## 1. 프로젝트 한 줄 요약
문서를 업로드하고 대화하는 RAG 챗봇. FastAPI 백엔드(`backend/`) + React/Vite 프론트(`frontend/`) + PostgreSQL(pgvector) + Redis(선택).
검색은 Vector + Keyword(tsvector) → RRF 결합(Hybrid), 쿼리 재작성 + HyDE 사용. 임베딩은 OpenAI `text-embedding-3-small`.

## 2. 로컬 실행 (Windows + WSL) — 함정 많음
- **Docker Desktop을 먼저 켜고** `docker start ragdb` (pgvector 컨테이너, 5432). 다른 `ib-*` 컨테이너들은 이 프로젝트와 무관.
- **백엔드 venv는 WSL(Linux)에서 만들어졌다** (`backend/venv/bin/...`). Windows의 `uvicorn.exe`로는 안 돌아간다.
  - WSL 배포판 이름은 `Ubuntu`. `wsl -d Ubuntu ...` 로 실행.
  - 백엔드: `cd backend && source venv/bin/activate && uvicorn main:app --reload` (첫 기동은 `/mnt/c` 때문에 1분 안팎 걸림. `Application startup complete` 확인)
  - 프론트: WSL에서 `cd frontend && npm run dev` → http://localhost:5173. **Node/npm은 WSL에만 있다** (Windows·Git Bash에는 없음).
  - Redis는 WSL에서 응답함(선택 기능). 꺼져 있으면 `sudo service redis-server start`.
- 프로젝트 경로에 **한글·공백**이 있다 (`바탕 화면`). 따옴표 필수.
  - Claude가 PowerShell/Git Bash에서 WSL 명령을 부를 때 인용이 자주 깨진다 → **bash 스크립트 파일을 scratchpad에 쓰고 `wsl -d Ubuntu -e bash /mnt/c/.../script.sh`로 실행**하는 방식이 안정적. 스크립트 안에서 `cd /mnt/c/Users/jaho3/OneDrive/*/it/study/rebootcam/Quest2/RAG_Project-Quest2`처럼 글롭으로 한글 구간을 피했다.
  - Git Bash에서 `wsl.exe` 인자의 `/mnt/...` 경로는 `C:/Program Files/Git/`이 앞에 붙어 깨진다 → PowerShell에서 호출.
  - PowerShell 5.1의 `Set-Content -Encoding utf8`은 BOM을 붙인다. 한글이 든 파일은 Write 도구로 쓰는 편이 안전.
- **Vite가 Windows 쪽 수정 파일을 감지 못한다** (`/mnt/c` 감시 한계). 프론트 파일을 바꿨으면 `npm run dev`를 재시작하고 새로고침. (백엔드 `--reload`는 감지됨.) `vite.config.ts`에 `usePolling`은 아직 안 넣었다.
- `while read` 반복문 안에서 `docker exec -i`를 쓰면 stdin을 먹어 첫 항목만 처리된다 → `-i`를 빼거나 `< /dev/null`.
- VS Code에서 localhost 링크가 VS Code 안에서 열리는 문제는 미해결. 사용자 settings.json에 `remote.autoForwardPorts: false`, `workbench.externalUriOpeners`(localhost → default)를 넣어 봤지만 효과 미확인. 브라우저 주소창에 직접 입력하는 게 확실.

## 3. LLM / API 키 상태
`.env`에 키가 있다 (**값은 절대 출력·커밋 금지**, `.env`는 git 추적 안 됨).
- **OpenAI**: 키 유효. 임베딩과 gpt-4o 계열에 쓰임. **유료 종량제**(구독과 별개). 문서 업로드·질문 임베딩에 항상 쓰이므로 이 키가 죽으면 검색 자체가 안 된다.
- **Claude(Anthropic)**: `ANTHROPIC_API_KEY`가 비어 있음. API 키 발급+크레딧 충전이 필요(Claude.ai 구독과 별개).
- **Groq / Google Gemini**: 키 유효(무료). 예전 모델명(Llama 3.x, Gemini 1.5/2.0)은 **서비스 종료**로 404였고, 현재 모델로 교체했다.
  - UI 노출 모델: Gemini `2.5-flash`(기본), `2.5-flash-lite`, `3.5-flash`, `3.8-flash` / Groq `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`
  - Groq 무료 한도(공식 문서 기준): 모델당 분당 30회·일 1,000회·분당 8K 토큰·일 200K 토큰. 질문 1번에 LLM이 약 4번(재작성·HyDE·답변·가독성 평가) 호출되고 RAG 컨텍스트가 커서 토큰이 먼저 바닥남. 모델별로 따로 계산되는 것으로 보이나 명시 확인은 못 함.
  - Gemini 무료 한도 숫자는 확인 못 함(AI Studio 대시보드에서만 보임).
  - 모델 이름은 자주 바뀐다. 쓰기 전에 각 제공사의 모델 목록 API로 확인할 것.
- **유료 모델(OpenAI/Claude)은 UI에서만 숨김**: `frontend/src/types/index.ts`의 `PAID_MODEL_OPTIONS`로 분리. 백엔드 코드(`services/llm/`)는 그대로. 다시 쓰려면 `MODEL_OPTIONS`에 합치면 됨(선택기가 유료 섹션을 자동 표시).
- 기본 provider/model은 `gemini` / `gemini-2.5-flash` (`routers/chat.py`, `routers/quiz.py`, `benchmark.py`).

## 4. DB 현황 (평가 기준 데이터)
- 14개 문서, **187청크**: 머신러닝교과서 ch1~ch8, 에이전트_엔지니어링1·2, 클로드코드_20260111, DB모델링, LLM_ch1_2, rag시스템구축하기, RAG_환경설정.
- 청크 크기 약 900자, 오버랩 200자 → 인접 청크에 같은 내용이 중복된다.
- `document_chunks.chunk_id` = `{문서UUID}_{청크번호}` (UNIQUE). 문서를 지우고 다시 올리면 UUID가 바뀌어 **평가 정답(Ground Truth, `retrieval-evaluation` 브랜치의 `backend/eval/questions.json`)의 chunk_id가 깨진다** → `filename`+`chunk_index`로 재매핑.

## 5. Git
- 원격: `jaho96/RAG_Project-Quest2`가 `jaho96/RAG-chat-with-evaluation`으로 **이동**됨. 이전 주소로도 push는 되지만 안내가 뜸. 필요하면 `git remote set-url origin https://github.com/jaho96/RAG-chat-with-evaluation.git` (사용자 확인 후).
- 브랜치: `main`(서비스 코드, 모델 교체 커밋 `dafd968`까지) / `retrieval-evaluation`(검색 성능 평가 작업, 아직 `main`에 병합하지 않음 — 6장 참고).
- **WSL 안의 `git status`는 CRLF 차이로 가짜 변경이 잔뜩 보인다.** 실제 상태는 Windows git(PowerShell/Git Bash)으로 확인.
- 커밋·푸시는 **사용자가 요청할 때만**. 커밋 메시지 끝에 Claude 공동 작성자 줄(시스템 지침)을 붙인다. `.env`·키·`backend/benchmark_result.json`은 커밋하지 않는다.

## 6. 진행 중인 작업: Retrieval 평가 (브랜치 `retrieval-evaluation`)
Vector-only vs Hybrid(Vector + Keyword + RRF) 검색 성능을 Recall@K / MRR / nDCG로 비교하는 작업. **관련 코드와 데이터(`backend/retrieval_eval.py`, `backend/retrieval_compare.py`, `backend/eval/`, `search()`의 `mode` 인자)는 `main`에 없고 `retrieval-evaluation` 브랜치에만 있다.**

이어서 하려면:
1. `git checkout retrieval-evaluation`
2. 그 브랜치의 `CLAUDE.md` 6장과 `backend/eval/README.md`를 먼저 읽는다.
3. 평가 기준(relevance 정의, Top-10 ranking 하나를 K=5/10 cutoff로 평가, linear gain 등)은 사용자와 합의한 것이므로 임의로 바꾸지 않는다.

## 7. 사용자와의 작업 방식 (지금까지 합의된 것)
- 한국어로 소통. 큰 변경은 **먼저 분석·계획을 보여주고 확인받은 뒤** 구현. "결과를 먼저 보여달라"는 요청이 많다.
- 평가 작업에서는 **결과를 좋게 보이도록 가공하지 않는다**. 정답(Ground Truth)을 자동 확정하지 않고 후보와 근거를 보여준 뒤 사용자가 기준을 정한다.
- 요청 범위 밖의 수정(검색 알고리즘 변경 등)을 하지 않는다. 기존 서비스 동작은 건드리지 않고 평가 경로에서만 분기한다.
- 모르는 것·확인 못 한 것은 "확인 못 함"이라고 말한다 (예: Gemini 무료 한도, VS Code 링크 설정 효과).

## 8. 다음에 할 만한 일 (미정, 사용자 결정 필요)
- 평가 결과 해석 및 발표 자료(PPT) 반영.
- 평가셋 확대(질문 수·카테고리 다양화). Ground Truth 추가 시 `eval/README.md` 기준을 따를 것.
- `vite.config.ts` `usePolling` 추가, 원격 URL 갱신, `main`에 평가 코드 병합 여부.
