"""v0 설정을 한곳에 모음. 경로, 접속 주소, 모델 이름만 두고 비밀값은 환경변수나 secrets/.env에서만 읽음."""

from __future__ import annotations

import os
from pathlib import Path

V0 = Path(__file__).resolve().parent
REPO = V0.parents[2]  # hybrid-ai 저장소 루트(teacher/graphrag/v0의 세 단계 위)

# 실행 결과: 활성 세대 파일 하나와 세대별 폴더
DATA = V0 / "data"
GENERATIONS = DATA / "generations"
ACTIVE_FILE = DATA / "active_generation.json"

# 세대 ID 앞머리. 이 저장소가 만든 세대만 gen-hai-로 시작하게 함. 같은 DB에 다른 실험 데이터가 섞여도
# 세대 ID가 겹치지 않고, 증분 색인과 tools/reset.py는 이 앞머리 세대만 건드림
# (2026-10-24까지는 Neo4j와 OpenSearch 볼륨을 hybrid-ai-lab과 함께 썼고, 지금은 hybrid-ai 전용 볼륨임)
GENERATION_TAG = "hai"

# 문서 유형별 그래프 스키마(graph_schema.json, approval.json, schema_spec.json). hands-on 실습 정답 폴더를 읽기만 함
SCHEMA_DIR = REPO / "hands-on" / "solutions" / "graphrag" / "schema" / "doc"
DOC_TYPES = ("regulation", "benefit_guide", "consult_log")

# 입력 청크: 이 저장소 RAG 인덱싱 예제가 만든 Chroma(collection card_docs)를 tools/export_chroma_chunks.py가
# v0 입력 꼴(prepared-chunks.json)로 바꿔 둔 파일
CHROMA_DIR = REPO / "hands-on" / "solutions" / "rag" / "indexing" / "data" / "chroma"
CHROMA_COLLECTION = "card_docs"
DEFAULT_CHUNKS = DATA / "chroma-chunks.json"

# S2 키워드 분석: 사람 검수를 통과한 카드 별칭(RAG 인덱싱 예제의 강사 제공 파일을 읽기만 함)
ALIASES_APPROVED = REPO / "hands-on" / "solutions" / "rag" / "indexing" / "aliases_approved.json"
LEXICAL_RULES = "rag-core_indexing-v1"  # 토큰화 규칙 판. lexical.py 규칙을 바꾸면 올려야 사전 검사가 새로 만듦

# 비밀값 파일(GROQ_API_KEY)
SECRET_FILE = REPO / "secrets" / ".env"

# Neo4j: backing-services/neo4j/compose.yml의 컨테이너 hybrid-ai-neo4j(APOC, GDS 포함). 비밀번호는 코드에 두지 않고
# 환경변수 NEO4J_PASSWORD, 없으면 compose 옆 .env 파일에서만 읽음
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_ENV_FILE = REPO / "backing-services" / "neo4j" / ".env"

# 검색엔진(OpenSearch): backing-services/opensearch/compose.yml의 컨테이너 hybrid-ai-opensearch. 세대마다 인덱스 하나: card_chunks-{세대 ID}
OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "http://127.0.0.1:9200")
INDEX_PREFIX = "card_chunks"

# LLM(K2 추출)
LLM_PROVIDER = "groq"
LLM_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")
LLM_CONCURRENCY = 4  # 동시 호출 수
LLM_RETRIES = 2  # 형식 오류가 나면 같은 입력으로 다시 묻는 횟수

# K8 커뮤니티 요약(선택 단계, 오케스트레이터 --communities로 켬)
COMMUNITY_SEED = 42  # GDS Leiden 씨앗. 고정해야 같은 그래프에서 같은 묶음이 나와 보고서를 재사용할 수 있음
COMMUNITY_MIN_SIZE = 3  # 엔티티가 이보다 적은 묶음은 요약하지 않음(한두 개짜리 묶음은 엔티티 설명으로 충분함)
COMMUNITY_MAX_ENTITIES = 120  # 보고서 입력에 넣는 엔티티 상한(큰 묶음이 LLM 입력 한도를 넘지 않게 함)

# 임베딩(S1 청크, K6 노드 설명, K8 커뮤니티 요약): KURE-v2. ~/.cache/huggingface/hub에 받아 둔 것만 씀
EMBED_MODEL = "nlpai-lab/KURE-v2"
EMBED_REVISION = "3431f86d399d666083890dbb882aced6708873bc"
EMBED_DIMENSION = 768
EMBED_MAX_SEQ_LENGTH = 800  # 특수 토큰을 포함한 입력 토큰 상한

# BM25 조절값(RAG 인덱싱 예제와 같음)
BM25_K1 = 1.5
BM25_B = 0.75
