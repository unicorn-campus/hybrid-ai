"""GraphRAG 인덱싱 예제 main: ① 세대 ID 발급 → ② 공통 단계 → ③ 인덱스 구축(KG 구축 K1 ~ K6, K8과 검색엔진 S1 ~ S3) → ④ 검증 → ⑤ 게시.

교재 30쪽 「인덱싱 워크플로우 구성안」의 전체 재색인(full)만 다룸(증분 색인과 K7은 다루지 않음).
단계마다 알맹이는 core_graph.py의 함수가 맡고, 이 파일은 설정값, 저장소 접속, LLM과 임베딩 호출, 순서, 단계별 출력을 맡음.

실행(이 폴더에서):
  ../.venv/Scripts/python.exe index_graph.py --run {별명}-s1 --sample      표본 10청크(수업용)
  ../.venv/Scripts/python.exe index_graph.py --run {별명}-f1               전체 260청크
옵션: --full-reindex(사전 검사 무시), --skip-communities(K8 생략), --reuse {폴더}(강사 배포 추출 결과 재사용),
      --chunks {파일}(Chroma 대신 청크 파일 입력)
"""

import argparse
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import chromadb
import neo4j
from dotenv import dotenv_values
from langchain_cohere import CohereEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from neo4j_graphrag.components.kg_writer import Neo4jWriter
from neo4j_graphrag.components.schema import GraphSchema
from neo4j_graphrag.components.types import Neo4jGraph
from neo4j_graphrag.llm import LLMInterface, LLMResponse
from opensearchpy import OpenSearch, helpers

import core_graph as core  # 교육생: 본인 코드로 바꾸려면 "import my_graph as core"
import kr_tokenizer

sys.stdout.reconfigure(encoding="utf-8")  # Windows 콘솔에서 한글이 깨지지 않게 함
logging.getLogger("neo4j_graphrag").setLevel(logging.ERROR)  # "LLMInterface is deprecated" 경고를 숨김(동작에는 영향 없음)
logging.getLogger("neo4j.notifications").setLevel(logging.ERROR)  # 빈 DB에서 첫 K6 때 나오는 속성 없음 알림을 숨김

# ---------------------------------------------------------------------------
# 설정값(상수). 교육생이 값을 바꿔 보며 결과 차이를 볼 수 있도록 한곳에 모음
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent  # 이 파일이 있는 indexer 폴더
ROOT_DIR = BASE_DIR.parents[3]  # indexer → graphrag → solutions → hands-on → 저장소 루트
DATA_DIR = BASE_DIR / "data"  # 실행 결과 폴더
GENERATIONS_DIR = DATA_DIR / "generations"  # 세대마다 폴더 하나(prepared-chunks, kg_prepared, community_reports, build_report)
ACTIVE_FILE = DATA_DIR / "active_generation.json"  # 활성 세대 파일. ⑤ 게시가 바꾸는 유일한 파일

# ② 입력: RAG 실습(W3)이 만든 Chroma. 읽기만 함
CHROMA_DIR = ROOT_DIR / "hands-on" / "solutions" / "rag" / "indexing" / "data" / "chroma"
COLLECTION_NAME = "card_docs"  # RAG 실습과 약속한 collection 이름
# 표본 모드(--sample)의 청크 10개: 약관 2(조항이 많은 쪽), 혜택 안내 4(한빛 가족돌봄), 상담 4(앞 상담을 가리키는 쌍 포함)
SAMPLE_CHROMA_IDS = ["D1-0005", "D1-0006", "D2-0067", "D2-0068", "D2-0069", "D2-0070",
                     "D3-0001", "D3-0002", "D3-0005", "D3-0006"]

# 문서 프로필(교재 31쪽 사전 검사 항목): 원천 메타데이터에 없는 문서 수준 값을 머리줄에 보탬.
# 약관 PDF의 메타데이터 쪽(버전 1.2, 시행 2027-01-15, 이전 판 1.1)을 옮긴 것으로, 약관 문서 노드(TermsDocument)의
# 고유 속성 version을 채움. 없으면 LLM이 파일 이름을 version에 넣는 일이 생김(2026-10-24 실측)
DOC_PROFILES = {"D1": {"version": "1.2", "effective_date": "2027-01-15", "supersedes": "1.1"}}

# 문서 유형별 그래프 스키마(스키마 설계 실습 결과). 읽기만 함
SCHEMA_DIR = ROOT_DIR / "hands-on" / "solutions" / "graphrag" / "schema" / "doc"
DOC_TYPES = ("regulation", "benefit_guide", "consult_log")  # 약관, 혜택 안내, 상담 기록

# S2 키워드 분석: 사람 검수를 통과한 카드 별칭(RAG 실습 강사 제공 파일). 읽기만 함
ALIASES_APPROVED_PATH = ROOT_DIR / "hands-on" / "solutions" / "rag" / "indexing" / "aliases_approved.json"
LEXICAL_RULES = "rag-core_indexing-v1"  # 토큰화 규칙 판. kr_tokenizer 규칙을 바꾸면 올려야 사전 검사가 새로 만듦

# 비밀값. 키 값은 코드, 주석, README에 절대 적지 않음
SECRETS_PATH = ROOT_DIR / "secrets" / ".env"  # GROQ_API_KEY, COHERE_API_KEY
NEO4J_ENV_PATH = ROOT_DIR / "backing-services" / "neo4j" / ".env"  # NEO4J_PASSWORD(환경변수가 없을 때)

# 저장소 접속. 다른 곳에 띄웠으면 환경변수로 넘김
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
OPENSEARCH_URL = os.environ.get("OPENSEARCH_URL", "http://127.0.0.1:9200")
NEO4J_CONNECT_TIMEOUT = 30  # 접속 제한 시간(초). 서버가 없을 때 오래 기다리지 않게 함

# 세대와 인덱스 이름
GENERATION_TAG = "lab"  # 세대 ID 앞머리 gen-lab-. 같은 DB의 다른 세대(v0의 gen-hai-)와 구분함
INDEX_PREFIX = "card_chunks"  # 검색엔진 인덱스 이름 card_chunks-{세대 ID}
ENTITY_INDEX = "kg_entity_embedding"  # K6 벡터 인덱스(교재 44쪽)
COMMUNITY_INDEX = "kg_community_embedding"  # K8 벡터 인덱스

# LLM(K2 추출, K8 보고서): Groq. JSON 모드로 묻고 temperature 0
LLM_MODEL = "openai/gpt-oss-120b"
LLM_CONCURRENCY = 2  # 동시 호출 수. 조별 키 하나를 여럿이 쓰므로 낮게 둠
LLM_RETRIES = 3  # 형식 오류가 나면 같은 입력으로 다시 묻는 횟수(Groq JSON 모드가 가끔 400을 내어 넉넉히 둠)
LLM_TIMEOUT = 90  # 호출 한 번의 제한 시간(초)

# 임베딩(S1 청크, K6 엔티티 설명, K8 보고서): Cohere. RAG 실습과 같은 모델과 키
EMBEDDING_MODEL = "embed-v5.0-fast"
EMBED_DIMENSION = 2048  # 벡터 길이. 검색엔진 매핑과 Neo4j 벡터 인덱스에 같은 값을 적음
EMBED_BATCH_SIZE = 96  # Cohere 한 요청에 넣을 수 있는 최대 건수

# BM25 조절값(RAG 실습과 같음). 검색엔진 인덱스 설정에 적음
BM25_K1 = 1.5
BM25_B = 0.75

# K8 커뮤니티 요약
COMMUNITY_SEED = 42  # GDS Leiden 씨앗. 고정해야 같은 그래프에서 같은 묶음이 나와 보고서를 재사용할 수 있음
COMMUNITY_MIN_SIZE = 3  # 엔티티가 이보다 적은 묶음은 요약하지 않음
COMMUNITY_MAX_ENTITIES = 120  # 보고서 입력에 넣는 엔티티 상한(큰 묶음이 LLM 입력 한도를 넘지 않게 함)
REPORT_VERSION = "v1"  # 보고서 판. 프롬프트를 바꾸면 올려야 옛 보고서를 재사용하지 않음

# 검색엔진 문서에 남기는 메타데이터(필터와 출처 표시용)
META_FIELDS = ("doc_key", "doc_type", "access_level", "source", "chroma_id", "card_id", "card_name", "product_id",
               "record_id", "channel", "consult_date", "member_pseudo_id")

# K8 보고서 프롬프트
REPORT_SYSTEM = ("너는 카드사 상담 지원용 지식 그래프의 묶음(커뮤니티)을 요약하는 분석가다. 주어진 엔티티와 관계만 근거로 쓰고, "
                 "없는 사실을 지어내지 않는다. 반드시 JSON 하나로만 답한다.")
REPORT_USER = """아래는 지식 그래프에서 서로 촘촘히 이어진 엔티티 묶음이다.
이 묶음이 무엇에 관한 것인지 상담사가 한눈에 알 수 있게 요약 보고서를 써라.

출력 형식(JSON):
{{"title": "묶음의 주제를 한 줄로(40자 이내)",
  "summary": "묶음 전체를 3 ~ 5문장으로 요약",
  "findings": [{{"text": "핵심 사실 한 문장", "entities": ["근거 엔티티 번호, 예: e3"]}}]}}
findings는 3 ~ 6개. 각 사실의 entities에는 근거가 된 엔티티 번호를 1개 이상 넣는다.
title, summary, findings의 text에는 e1 같은 엔티티 번호를 쓰지 말고 내용으로 풀어 쓴다. 번호는 entities 칸에만 쓴다.

엔티티:
{entities}

관계:
{relations}"""
ENTITY_REF = re.compile(r"\s*\(?\be\d+(?:\s*(?:~|-|,|와|및)\s*e?\d+)*\)?")  # 보고서 본문에 남은 e3 같은 번호를 지움


# ---------------------------------------------------------------------------
# 작은 도구: 출력, 파일, 해시, 비밀값, 접속
# ---------------------------------------------------------------------------
def log(message: str) -> None:
    """시각을 붙여 한 줄 출력함. 단계가 얼마나 걸리는지 보려는 것임."""
    print(time.strftime("%H:%M:%S"), message, flush=True)


def load_json(path: Path):
    """JSON 파일을 읽어 파이썬 값으로 돌려줌."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    """임시 파일에 다 쓴 뒤 바꿔 끼움. 쓰다가 멈춰도 반쯤 쓴 파일이 남지 않게 함."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)


def sha256_file(path: Path) -> str:
    """파일 내용의 SHA-256 해시(설정 지문에 씀)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_secret(name: str) -> str:
    """secrets/.env에서 값 하나를 읽음. 없으면 어디에 넣을지 안내하고 종료함."""
    values = dotenv_values(SECRETS_PATH) if SECRETS_PATH.exists() else {}
    value = (values.get(name) or "").strip()
    if not value:
        raise SystemExit(f"{SECRETS_PATH}에 {name}=... 줄이 필요함(키는 강사에게 받음)")
    return value


def neo4j_password() -> str:
    """환경변수 NEO4J_PASSWORD를 먼저 쓰고, 없으면 Neo4j compose 옆 .env에서 읽음(값은 출력하지 않음)."""
    password = os.environ.get("NEO4J_PASSWORD")
    if not password and NEO4J_ENV_PATH.exists():
        password = (dotenv_values(NEO4J_ENV_PATH).get("NEO4J_PASSWORD") or "").strip()
    if not password:
        raise SystemExit(f"Neo4j 비밀번호가 없음: 환경변수 NEO4J_PASSWORD 또는 {NEO4J_ENV_PATH}에 NEO4J_PASSWORD=...")
    return password


def neo4j_driver():
    """Neo4j 드라이버를 만듦(접속 제한 시간 적용). 쓰는 쪽이 close()함."""
    return neo4j.GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, neo4j_password()),
                                      connection_timeout=NEO4J_CONNECT_TIMEOUT)


def opensearch_client() -> OpenSearch:
    """OpenSearch 클라이언트를 만듦(제한 시간 60초, 재시도 3번)."""
    return OpenSearch(hosts=[OPENSEARCH_URL], timeout=60, max_retries=3, retry_on_timeout=True)


def index_name(generation: str) -> str:
    """세대 ID로 검색엔진 인덱스 이름(card_chunks-{세대 ID})을 만듦."""
    return f"{INDEX_PREFIX}-{generation}"


# ---------------------------------------------------------------------------
# 모델: LLM(Groq, LangChain ChatGroq)과 임베딩(Cohere, LangChain CohereEmbeddings)
# ---------------------------------------------------------------------------
class GroqLLM(LLMInterface):
    """LangChain ChatGroq를 neo4j-graphrag 추출기가 부르는 LLMInterface 모양으로 감싼 것.

    추출기는 invoke(프롬프트) → LLMResponse(content=JSON 글)만 필요로 함. JSON 모드와 재시도(429, 5xx)는 ChatGroq가 맡음.
    """

    def __init__(self, model_name: str, api_key: str) -> None:
        super().__init__(model_name=model_name)
        self.chat = ChatGroq(
            model=model_name,
            api_key=api_key,
            temperature=0,
            max_retries=6,  # 429(호출 제한)와 5xx는 기다렸다 다시 부름
            request_timeout=LLM_TIMEOUT,
            reasoning_effort="medium",  # gpt-oss 계열의 추론 강도. 추론 글은 content에 섞이지 않음
            model_kwargs={"response_format": {"type": "json_object"}},  # 답을 JSON 하나로만 받음
        )
        self.usage = {"calls": 0, "total_tokens": 0}
        self._lock = threading.Lock()  # 여러 스레드가 usage를 함께 더하므로 잠금

    def chat_json(self, prompt: str, system: str | None = None) -> str:
        """JSON 모드로 한 번 묻고 응답 글을 그대로 돌려줌(K2 추출과 K8 보고서가 함께 씀). 부수효과: usage에 더함."""
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))
        response = self.chat.invoke(messages)
        content = response.content
        if isinstance(content, list):  # 일부 모델은 조각 목록으로 줌. 글 조각만 이어 붙임
            content = "".join(part if isinstance(part, str) else part.get("text", "") for part in content)
        usage = response.usage_metadata or {}
        with self._lock:
            self.usage["calls"] += 1
            self.usage["total_tokens"] += int(usage.get("total_tokens", 0))
        return content

    def invoke(self, input: str, message_history=None, system_instruction=None) -> LLMResponse:
        """추출기가 부르는 동기 호출. 응답 JSON을 그래프 꼴로 다듬어 LLMResponse로 돌려줌."""
        return LLMResponse(content=tidy_graph_json(self.chat_json(input, system_instruction)))

    async def ainvoke(self, input: str, message_history=None, system_instruction=None) -> LLMResponse:
        """추출기가 부르는 비동기 호출. 실제 호출은 스레드에서 invoke로 함."""
        # 추출기는 비동기로 부르지만 실제 호출은 스레드에서 동기로 함(이벤트 루프마다 클라이언트를 새로 만들지 않아도 됨)
        return await asyncio.to_thread(self.invoke, input, message_history, system_instruction)


def tidy_graph_json(content: str) -> str:
    """LLM 응답을 그래프 꼴로 다듬음: 정해진 칸 밖 키 제거, id는 글자로, 빈 속성 제거. 사소한 형식 차이로 버려지지 않게 함."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content  # JSON이 아니면 그대로 돌려줌(추출기가 형식 오류로 처리하고 다시 묻게 됨)

    def plain(value):
        """속성 값은 글자, 숫자, 참거짓, 그 목록만 허용. 중첩 dict는 글자로 바꿈."""
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list) and all(isinstance(x, (str, int, float, bool)) for x in value):
            return value
        return json.dumps(value, ensure_ascii=False)

    def props(obj: dict) -> dict:
        result = {}
        for key, value in (obj.get("properties") or {}).items():
            if plain(value) is not None:
                result[key] = plain(value)
        return result

    nodes = []
    for node in data.get("nodes", []):
        if isinstance(node, dict):
            nodes.append({"id": str(node.get("id")), "label": str(node.get("label")), "properties": props(node)})
    relationships = []
    for rel in data.get("relationships", []):
        if isinstance(rel, dict):
            relationships.append({"type": str(rel.get("type")), "start_node_id": str(rel.get("start_node_id")),
                                  "end_node_id": str(rel.get("end_node_id")), "properties": props(rel)})
    return json.dumps({"nodes": nodes, "relationships": relationships}, ensure_ascii=False)


def make_llm() -> GroqLLM:
    """secrets/.env의 GROQ_API_KEY로 GroqLLM을 만듦."""
    return GroqLLM(LLM_MODEL, read_secret("GROQ_API_KEY"))


_embedder = None


def embed_texts(texts: list[str]) -> list[list[float]]:
    """글 목록을 Cohere로 임베딩함(색인용 input_type search_document). 96건씩 나눠 부름.

    S1(청크), K6(엔티티 설명), K8(보고서)이 모두 이 함수를 씀. 질문 임베딩은 check_graph.py가 embed_query로 따로 함.
    """
    global _embedder
    if not texts:
        return []
    if _embedder is None:  # 처음 부를 때 한 번만 만듦
        _embedder = CohereEmbeddings(model=EMBEDDING_MODEL, cohere_api_key=read_secret("COHERE_API_KEY"), max_retries=5)
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        vectors.extend(_embedder.embed_documents(batch))
    if vectors and len(vectors[0]) != EMBED_DIMENSION:
        raise SystemExit(f"임베딩 차원이 설정과 다름: {len(vectors[0])} != {EMBED_DIMENSION}")
    return vectors


# ---------------------------------------------------------------------------
# 스키마와 설정 지문
# ---------------------------------------------------------------------------
def load_schemas() -> dict:
    """문서 유형마다 graph_schema.json, 추출 단위 규칙(approval.json), 머리줄 칸(schema_spec.json)을 읽음."""
    schemas = {}
    for doc_type in DOC_TYPES:
        folder = SCHEMA_DIR / doc_type
        path = folder / "graph_schema.json"
        if not path.exists():
            continue
        approval = load_json(folder / "approval.json")
        schemas[doc_type] = {
            "schema": GraphSchema.from_file(str(path)),
            "unit_rule": approval.get("extraction_unit_rule"),  # 없으면 청크를 그대로 추출 단위로 씀
            "header": load_json(folder / "schema_spec.json").get("metadata_header", []),
            "signature": sha256_file(path),  # 스키마가 바뀌면 보관한 추출 결과를 다시 쓰지 않음
        }
    return schemas


def config_signature() -> str:
    """처리 설정 지문: 스키마 파일, LLM, 임베딩, BM25 값, 토큰화 규칙과 승인 별칭이 하나라도 바뀌면 사전 검사가 생략하지 않음."""
    parts = []
    for doc_type in DOC_TYPES:
        path = SCHEMA_DIR / doc_type / "graph_schema.json"
        if path.exists():
            parts.append(sha256_file(path))
    parts += [LLM_MODEL, EMBEDDING_MODEL, str(EMBED_DIMENSION), str(BM25_K1), str(BM25_B), LEXICAL_RULES]
    parts.append(json.dumps(DOC_PROFILES, ensure_ascii=False, sort_keys=True))  # 문서 프로필이 바뀌어도 새로 만듦
    if ALIASES_APPROVED_PATH.exists():
        parts.append(sha256_file(ALIASES_APPROVED_PATH))
    return core.sha256_text("|".join(parts))


# ---------------------------------------------------------------------------
# 시작 검사: 저장소, 플러그인, 벡터 인덱스 차원, 키
# ---------------------------------------------------------------------------
def check_environment(driver, os_client: OpenSearch, want_communities: bool) -> bool:
    """실행에 필요한 것을 한 번에 확인하고 모자라면 할 일을 안내함. 반환값: K8을 돌릴 수 있는지(GDS 있음)."""
    read_secret("GROQ_API_KEY")
    read_secret("COHERE_API_KEY")
    log("시작 검사: 키 2개 있음(secrets/.env)")
    try:
        records, _, _ = driver.execute_query("RETURN apoc.version() AS apoc")
        log(f"시작 검사: Neo4j 접속 {NEO4J_URI}, APOC {records[0]['apoc']}")
    except Exception as error:
        raise SystemExit(f"Neo4j 접속 또는 APOC 확인 실패({NEO4J_URI}): {type(error).__name__}: {str(error)[:120]}\n"
                         "  → backing-services 폴더에서 docker compose -f neo4j/compose.yml up -d 로 띄우고 healthy를 확인함")
    gds_ok = True
    try:
        records, _, _ = driver.execute_query("RETURN gds.version() AS gds")
        log(f"시작 검사: GDS {records[0]['gds']}")
    except Exception:
        gds_ok = False
        if want_communities:
            log("시작 검사: GDS가 없어 K8 커뮤니티 요약을 건너뜀(neo4j/README.md 「gds.version을 찾지 못함」 참고)")
    # 같은 이름의 벡터 인덱스가 다른 차원으로 있으면 IF NOT EXISTS 때문에 새로 만들지 못해 저장한 벡터가 검색되지 않음
    records, _, _ = driver.execute_query(
        "SHOW VECTOR INDEXES YIELD name, options RETURN name, options.indexConfig['vector.dimensions'] AS dim")
    for record in records:
        if record["name"] in (ENTITY_INDEX, COMMUNITY_INDEX) and record["dim"] != EMBED_DIMENSION:
            raise SystemExit(f"Neo4j에 {record['name']} 인덱스가 {record['dim']}차원으로 이미 있음(이 실습은 {EMBED_DIMENSION}차원)\n"
                             f"  → 다른 실습 데이터임. DROP INDEX {record['name']} 로 지우거나 실습용 Neo4j를 따로 띄움")
    try:
        info = os_client.info()
        log(f"시작 검사: OpenSearch 접속 {OPENSEARCH_URL}, 판 {info['version']['number']}")
    except Exception as error:
        raise SystemExit(f"OpenSearch 접속 실패({OPENSEARCH_URL}): {type(error).__name__}\n"
                         "  → backing-services 폴더에서 docker compose -f opensearch/compose.yml up -d")
    return gds_ok


# ---------------------------------------------------------------------------
# ② 공통 단계: 입력 읽기와 청크 파일 고정
# ---------------------------------------------------------------------------
def read_chroma_rows(sample: bool) -> list[dict]:
    """RAG 실습 Chroma에서 본문과 메타데이터를 읽어 chroma_id 순서로 돌려줌. 벡터는 읽지 않음(S1이 다시 임베딩함)."""
    if not (CHROMA_DIR / "chroma.sqlite3").exists():
        raise SystemExit(f"RAG 실습 Chroma가 없음: {CHROMA_DIR}\n"
                         "  → hands-on/solutions/rag/indexing/index_docs.py 를 먼저 실행하거나 강사 배포 data/를 복사함")
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    collection = client.get_collection(COLLECTION_NAME)
    result = collection.get(include=["documents", "metadatas"])
    rows = []
    for chroma_id, text, metadata in zip(result["ids"], result["documents"], result["metadatas"]):
        if sample and chroma_id not in SAMPLE_CHROMA_IDS:
            continue
        profile = DOC_PROFILES.get(chroma_id[:2], {})  # 문서 프로필 값을 먼저 깔고 Chroma 메타데이터가 덮어씀
        rows.append({"chroma_id": chroma_id, "text": text, "metadata": {**profile, **metadata}})
    rows.sort(key=lambda row: row["chroma_id"])  # D1-0001, D1-0002, … 순서가 문서 안 순서임
    return rows


def read_chunk_file(path: Path, sample: bool) -> list[dict]:
    """강사가 배포한 prepared-chunks.json을 입력으로 씀(--chunks). 표본이면 같은 chroma_id만 고름."""
    chunks = load_json(path)
    if sample:
        chunks = [c for c in chunks if c["metadata"].get("chroma_id") in SAMPLE_CHROMA_IDS]
    return chunks


def read_active() -> dict | None:
    """활성 세대 파일을 읽음. 없으면 None."""
    return load_json(ACTIVE_FILE) if ACTIVE_FILE.exists() else None


def clean_leftovers(driver, os_client: OpenSearch, generation: str) -> None:
    """중단 뒤 같은 실행 이름으로 다시 돌릴 때, 그 세대에 남은 노드와 검색엔진 인덱스를 지우고 처음부터 다시 만듦.

    K4는 노드를 새로 만들기(CREATE)만 하므로, 지우지 않으면 청크 노드가 두 벌이 되어 ④ 검증에 걸림.
    """
    records, _, _ = driver.execute_query(
        "MATCH (n {generation: $g}) WITH n LIMIT 100000 DETACH DELETE n RETURN count(*) AS n", g=generation)
    deleted_nodes = records[0]["n"]
    deleted_index = False
    if os_client.indices.exists(index=index_name(generation)):
        os_client.indices.delete(index=index_name(generation))
        deleted_index = True
    if deleted_nodes or deleted_index:
        log(f"① 같은 세대의 흔적을 지움(중단 뒤 재실행): 노드 {deleted_nodes}개, 검색엔진 인덱스 {'1개' if deleted_index else '없음'}")


# ---------------------------------------------------------------------------
# ③ KG 구축: K2 병렬 호출, K4 쓰기, K5 뒤 정리, K8 보고서
# ---------------------------------------------------------------------------
def k2_k3_extract(units: list[dict], schemas: dict, previous: dict | None) -> dict:
    """단위마다 LLM 추출(K2)과 가지치기(K3)를 하되, 앞 세대 결과와 본문 해시와 스키마 지문이 같은 단위는 재사용함.

    부수효과: units의 각 항목에 graph(또는 error), reused, schema_signature를 채움.
    반환값: {"llm_units": LLM을 부른 단위 수, "reused": 재사용 수, "usage": 토큰 사용량}.
    """
    # 재사용 열쇠: 문서 유형, 본문 해시, 스키마 지문, 머리줄(메타데이터). 하나라도 다르면 LLM에 다시 물음
    cache = {}
    for unit in (previous or {}).get("units", []):
        if "graph" in unit:
            cache[(unit["doc_type"], unit["text_hash"], unit["schema_signature"], unit.get("header_text", ""))] = unit["graph"]
    todo = []
    for unit in units:
        unit["schema_signature"] = schemas[unit["doc_type"]]["signature"]
        unit["header_text"] = core.head_line(unit["metadata"], schemas[unit["doc_type"]]["header"])
        hit = cache.get((unit["doc_type"], unit["text_hash"], unit["schema_signature"], unit["header_text"]))
        if hit is not None:
            unit["graph"] = hit
            unit["reused"] = True
        else:
            todo.append(unit)
    log(f"[K2] LLM 추출 {len(todo)}개, 앞 결과 재사용 {len(units) - len(todo)}개 (동시 {LLM_CONCURRENCY}건)")

    usage = {"calls": 0, "total_tokens": 0}
    if todo:
        llm = make_llm()

        def work(unit: dict) -> dict:
            return core.extract_one(unit, schemas[unit["doc_type"]], llm, LLM_RETRIES)

        done = 0
        with ThreadPoolExecutor(max_workers=LLM_CONCURRENCY) as pool:
            for unit, result in zip(todo, pool.map(work, todo)):
                unit.update(result)
                done += 1
                if done % 20 == 0:
                    log(f"[K2] {done}/{len(todo)}개 추출")
        usage = dict(llm.usage)
    return {"llm_units": len(todo), "reused": len(units) - len(todo), "usage": usage}


def header_fill_rate(units: list[dict], schemas: dict) -> dict:
    """문서 유형별로 머리줄 칸이 몇 %나 채워졌는지(Chroma 메타데이터에 없는 칸은 비어 감)."""
    rates = {}
    for doc_type, spec in schemas.items():
        fields = spec["header"]
        rows = [u for u in units if u["doc_type"] == doc_type]
        if not rows or not fields:
            continue
        filled = 0
        for unit in rows:
            for field in fields:
                if unit["metadata"].get(field) not in (None, ""):
                    filled += 1
        rates[doc_type] = round(100 * filled / (len(rows) * len(fields)))
    return rates


def k4_write(driver, nodes: list, relationships: list) -> None:
    """Neo4jWriter로 노드와 관계를 한 번에 씀. 노드는 새로 만들고(합치지 않음), 임시 ID로 관계 양 끝을 찾은 뒤 임시 ID는 지움."""
    asyncio.run(Neo4jWriter(driver).run(Neo4jGraph(nodes=nodes, relationships=relationships)))


def dedup_from_chunk(driver, generation: str) -> int:
    """같은 엔티티와 같은 청크 사이의 FROM_CHUNK를 하나만 남김(K5가 노드를 합치면 겹칠 수 있음. 보통 0건, 안전장치)."""
    records, _, _ = driver.execute_query(
        "MATCH (e:__Entity__ {generation: $g})-[r:FROM_CHUNK]->(c:Chunk {generation: $g}) "
        "WITH e, c, collect(r) AS rs WHERE size(rs) > 1 "
        "FOREACH (x IN tail(rs) | DELETE x) RETURN sum(size(rs) - 1) AS n", g=generation)
    return records[0]["n"] or 0


def entity_key(label: str, props: dict) -> str:
    """세대와 실행이 바뀌어도 같은 엔티티면 같은 키. Neo4j 내부 ID는 실행마다 바뀌어 묶음 지문에 쓸 수 없음."""
    clean = {k: v for k, v in props.items() if k not in core.SYSTEM_PROPS}
    return label + "|" + json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str)


def read_entity_graph(driver, generation: str) -> tuple[list[dict], list[tuple[int, int, str]]]:
    """K8 입력: 세대의 엔티티(키순 정렬, 번호 매김)와 엔티티 사이 관계(번호, 번호, 이름). 청크 노드와 FROM_CHUNK는 뺌."""
    records, _, _ = driver.execute_query(
        "MATCH (n:__Entity__ {generation: $g}) "
        "RETURN elementId(n) AS id, [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "properties(n) AS props", g=generation)
    entities = []
    for record in records:
        entity = {"id": record["id"], "label": record["label"], "props": dict(record["props"])}
        entity["key"] = entity_key(entity["label"], entity["props"])
        entities.append(entity)
    entities.sort(key=lambda e: e["key"])
    position = {entity["id"]: number for number, entity in enumerate(entities)}
    records, _, _ = driver.execute_query(
        "MATCH (a:__Entity__ {generation: $g})-[r]->(b:__Entity__ {generation: $g}) "
        "RETURN elementId(a) AS a, elementId(b) AS b, type(r) AS t", g=generation)
    relations = set()
    for record in records:
        if record["a"] in position and record["b"] in position:
            relations.add((position[record["a"]], position[record["b"]], record["t"]))
    return entities, sorted(relations)


def member_hash(entities: list[dict], members: list[int], relations: list) -> str:
    """묶음 지문: 보고서 판, 구성원 키, 묶음 안 관계로 만듦. 하나라도 바뀌면 보고서를 다시 씀."""
    inside = set(members)
    inner = sorted(f"{entities[a]['key']}->{t}->{entities[b]['key']}" for a, b, t in relations
                   if a in inside and b in inside)
    return core.sha256_text("\n".join([REPORT_VERSION] + [entities[i]["key"] for i in members] + inner))


def entity_line(number: int, entity: dict) -> str:
    """보고서 입력에 넣는 엔티티 한 줄: e3. Proposal: content=..., decision=..."""
    return f"e{number}. " + core.entity_description(entity["label"], entity["props"])[:300]


def short_name(entity: dict) -> str:
    """보고서 근거 표시용 짧은 이름: 라벨과 첫 속성 값."""
    values = [str(v) for k, v in sorted(entity["props"].items()) if k not in core.SYSTEM_PROPS]
    return f"{entity['label']}({(values[0] if values else '')[:40]})"


def summarize_community(llm: GroqLLM, entities: list[dict], members: list[int], relations: list) -> dict:
    """묶음 하나를 글로 바꿔 LLM에 보내고 보고서(title, summary, findings)를 받음. 큰 묶음은 관계가 많은 엔티티부터 상한까지."""
    inside = set(members)
    degree = {i: 0 for i in members}
    for a, b, _ in relations:
        if a in inside and b in inside:
            degree[a] += 1
            degree[b] += 1
    shown = sorted(sorted(members, key=lambda i: (-degree[i], i))[:COMMUNITY_MAX_ENTITIES])
    refs = {f"e{k}": i for k, i in enumerate(shown, 1)}
    back = {i: ref for ref, i in refs.items()}
    lines = [entity_line(k, entities[i]) for k, i in enumerate(shown, 1)]
    rels = [f"{back[a]} -[{t}]-> {back[b]}" for a, b, t in relations if a in back and b in back]
    prompt = REPORT_USER.format(entities="\n".join(lines), relations="\n".join(rels) or "(없음)")

    def plain(text) -> str:
        return re.sub(r"\s{2,}", " ", ENTITY_REF.sub("", str(text))).strip()

    for attempt in range(LLM_RETRIES + 1):  # 형식 오류는 같은 입력으로 다시 물음
        try:
            data = json.loads(llm.chat_json(prompt, REPORT_SYSTEM))
            findings = []
            for finding in data.get("findings") or []:
                names = [short_name(entities[refs[r]]) for r in finding.get("entities") or [] if r in refs]
                findings.append(f"{plain(finding.get('text', ''))} [근거: {', '.join(names) or '없음'}]")
            if not data.get("title") or not data.get("summary"):
                raise ValueError("title 또는 summary가 비어 있음")
            return {"title": plain(data["title"]), "summary": plain(data["summary"]), "findings": findings}
        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as error:
            if attempt == LLM_RETRIES:
                raise
            log(f"[K8 재시도 {attempt + 1}] 보고서 형식 오류: {type(error).__name__}")
    raise RuntimeError("도달하지 않음")


def k8_summarize(driver, generation: str, run_id: str, cache: dict) -> tuple[dict, dict]:
    """K8 전체: 엔티티 그래프 읽기 → Leiden 묶기(core) → 보고서(LLM, 재사용) → 임베딩 → 행 만들기(core) → 쓰기(core).

    반환값: (실행 결과 요약, 이번 세대의 {묶음 지문: 보고서}). 호출한 쪽이 기록 파일로 저장함.
    """
    entities, relations = read_entity_graph(driver, generation)
    edges = sorted({(min(a, b), max(a, b)) for a, b, _ in relations if a != b})
    graph_name = "k8-" + core.sha256_text(generation + "|" + run_id)[:12]
    groups = core.detect_communities(driver, graph_name, [e["id"] for e in entities], edges, COMMUNITY_SEED)
    hashes = [member_hash(entities, g, relations) for g in groups]
    targets = [(g, h) for g, h in zip(groups, hashes) if len(g) >= COMMUNITY_MIN_SIZE]
    todo = [(g, h) for g, h in targets if h not in cache]
    log(f"[K8] 엔티티 {len(entities)}개, 관계 {len(relations)}개 → 묶음 {len(groups)}개, "
        f"엔티티 {COMMUNITY_MIN_SIZE}개 이상 {len(targets)}개, 보고서 LLM {len(todo)}번, 재사용 {len(targets) - len(todo)}개")

    reports = {}
    usage = {"calls": 0, "total_tokens": 0}
    if todo:
        llm = make_llm()
        with ThreadPoolExecutor(max_workers=LLM_CONCURRENCY) as pool:
            made = list(pool.map(lambda item: summarize_community(llm, entities, item[0], relations), todo))
        for (_, h), report in zip(todo, made):
            reports[h] = report
        usage = dict(llm.usage)
    for _, h in targets:
        if h in cache:
            reports[h] = dict(cache[h])
    need_vector = [h for _, h in targets if "embedding" not in reports[h]]
    texts = [reports[h]["title"] + "\n" + reports[h]["summary"] + "\n" + "\n".join(reports[h]["findings"])
             for h in need_vector]
    for h, vector in zip(need_vector, embed_texts(texts)):
        reports[h]["embedding"] = vector

    rows = core.build_community_rows(groups, hashes, entities, reports, COMMUNITY_MIN_SIZE)
    core.k8_write_communities(driver, generation, run_id, rows, EMBED_DIMENSION, COMMUNITY_INDEX)
    for row in rows[:3]:
        log(f"      보고서 예: 「{row['title']}」 (엔티티 {row['size']}개)")
    result = {"entities": len(entities), "relations": len(relations), "groups": len(groups),
              "summarized": len(targets), "llm_calls": len(todo), "reused": len(targets) - len(todo),
              "usage": usage}
    return result, reports


def verify_communities(driver, generation: str) -> dict:
    """④ 검증 추가 항목(K8을 돌렸을 때만): 요약과 임베딩이 빠진 Community, 빈 묶음, 세대 밖 구성원을 셈."""
    records, _, _ = driver.execute_query(
        "MATCH (c:Community {generation: $g}) OPTIONAL MATCH (e)-[:IN_COMMUNITY]->(c) "
        "WITH c, collect(e) AS ms RETURN count(c) AS communities, "
        "sum(CASE WHEN c.summary IS NULL OR c.summary = '' OR c.embedding IS NULL THEN 1 ELSE 0 END) AS incomplete, "
        "sum(CASE WHEN size(ms) = 0 THEN 1 ELSE 0 END) AS empty, "
        "sum(size([m IN ms WHERE NOT m:__Entity__ OR m.generation <> $g])) AS foreign_members", g=generation)
    result = dict(records[0])
    result["ok"] = (result["communities"] > 0 and result["incomplete"] == 0 and result["empty"] == 0
                    and result["foreign_members"] == 0)
    return result


# ---------------------------------------------------------------------------
# ③ 검색엔진 인덱싱: 앞 세대 벡터 읽기, 매핑, ④ 검증용 읽기
# ---------------------------------------------------------------------------
def read_old_vectors(os_client: OpenSearch, index: str | None) -> dict[str, list[float]]:
    """활성 세대 인덱스에서 {본문 해시: 벡터}를 읽음(S1 벡터 재사용). 인덱스가 없으면 빈 dict."""
    if not index or not os_client.indices.exists(index=index):
        return {}
    old = {}
    for hit in helpers.scan(os_client, index=index, query={"_source": ["text_hash", "embedding"]}):
        old.setdefault(hit["_source"]["text_hash"], hit["_source"]["embedding"])
    return old


def index_mapping(tokenizer_meta: dict) -> dict:
    """벡터(kNN)와 키워드(BM25)를 한 인덱스에 둠. 사전 기록은 _meta에 남겨 검색 쪽이 같은 토크나이저를 만들게 함(교재 53쪽)."""
    keyword_fields = {name: {"type": "keyword"} for name in META_FIELDS}
    return {
        "settings": {"index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 0,
                               "similarity": {"bm25_lab": {"type": "BM25", "k1": BM25_K1, "b": BM25_B}}}},
        "mappings": {
            "_meta": {"tokenizer": tokenizer_meta},
            "properties": {
                "chunk_id": {"type": "keyword"}, "doc_id": {"type": "keyword"}, "text_hash": {"type": "keyword"},
                "text": {"type": "text", "index": False},  # 보여 주기용. 색인하지 않음
                "text_tokens": {"type": "text", "analyzer": "whitespace", "similarity": "bm25_lab"},  # 키워드 역색인
                "embedding": {"type": "knn_vector", "dimension": EMBED_DIMENSION,  # 벡터 색인(HNSW)
                              "method": {"name": "hnsw", "engine": "lucene", "space_type": "cosinesimil"}},
                **keyword_fields}}}


def search_chunk_ids(os_client: OpenSearch, index: str) -> set[str]:
    """④ 검증용: 인덱스에 들어 있는 청크 ID 전체(없으면 빈 집합)."""
    if not os_client.indices.exists(index=index):
        return set()
    return {h["_source"]["chunk_id"] for h in helpers.scan(os_client, index=index, query={"_source": ["chunk_id"]})}


def graph_chunk_ids(driver, generation: str) -> list[str]:
    """④ 검증용: 이 세대 청크 노드의 chunk_id 전체. 중복을 그대로 돌려줘 청크 하나에 노드가 둘인 경우도 잡게 함."""
    records, _, _ = driver.execute_query(
        "MATCH (c:Chunk {generation: $g}) RETURN collect(c.chunk_id) AS ids", g=generation)
    return list(records[0]["ids"])


def label_counts(driver, generation: str) -> dict[str, int]:
    """요약 출력용: 이 세대 엔티티의 라벨별 수."""
    records, _, _ = driver.execute_query(
        "MATCH (n:__Entity__ {generation: $g}) WITH [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label "
        "RETURN label, count(*) AS c ORDER BY c DESC", g=generation)
    return {r["label"]: r["c"] for r in records}


# ---------------------------------------------------------------------------
# 전체 흐름
# ---------------------------------------------------------------------------
def run(args) -> None:
    """① ~ ⑤를 순서대로 실행함(명령줄 인자 args를 받음)."""
    started = time.time()
    driver = neo4j_driver()
    os_client = opensearch_client()
    gds_ok = check_environment(driver, os_client, want_communities=not args.skip_communities)
    communities = gds_ok and not args.skip_communities

    # ② 공통 단계(앞부분): 입력을 읽어 청크 한 건으로 만듦. 세대 ID의 사전 검사에 청크 지문이 필요해 ①보다 먼저 읽음
    if args.chunks:
        chunks = read_chunk_file(Path(args.chunks), args.sample)
        log(f"② 공통 단계: 청크 파일 {args.chunks}에서 {len(chunks)}개 읽음")
    else:
        rows = read_chroma_rows(args.sample)
        chunks = core.prepare_chunks(rows)
        log(f"② 공통 단계: Chroma {COLLECTION_NAME}에서 {len(rows)}개 읽어 청크로 만듦")
    by_type = {}
    for chunk in chunks:
        by_type[chunk["doc_type"]] = by_type.get(chunk["doc_type"], 0) + 1
    log(f"      문서 유형별 {by_type}, 문서 {len({c['doc_id'] for c in chunks})}개. 예) {chunks[0]['chunk_id']}")
    input_sha256 = core.sha256_text(json.dumps(chunks, ensure_ascii=False, sort_keys=True))

    # ① 세대 ID 발급과 사전 검사
    active = read_active()
    issued = core.issue_generation(args.run, active, input_sha256, config_signature(), args.full_reindex, GENERATION_TAG)
    generation = issued["generation"]
    if issued["skip"]:
        log(f"① 세대 ID {generation} → 사전 검사: 입력과 설정이 활성 세대 {active['generation']}와 같아 할 일 없음"
            "(그래도 만들려면 --full-reindex)")
        return
    if active and generation == active["generation"]:
        raise SystemExit(f"세대 {generation}는 지금 활성 세대임: 전체 재색인은 새 실행 이름(--run)으로 해야 함")
    log(f"① 세대 ID {generation}")
    clean_leftovers(driver, os_client, generation)
    run_id = f"{args.run}@{time.strftime('%Y%m%d%H%M%S')}"

    # ② 공통 단계(뒷부분): 청크 파일을 세대 폴더에 고정
    gen_dir = GENERATIONS_DIR / generation
    save_json(gen_dir / "prepared-chunks.json", chunks)
    log(f"② 공통 단계: 청크 {len(chunks)}개를 {gen_dir.relative_to(BASE_DIR).as_posix()}/prepared-chunks.json 에 고정")

    # 앞 결과(재사용 대상): --reuse 폴더가 있으면 그것, 없으면 활성 세대 폴더
    previous_dir = Path(args.reuse) if args.reuse else (GENERATIONS_DIR / active["generation"] if active else None)
    previous_kg = None
    previous_reports = {}
    if previous_dir and (previous_dir / "kg_prepared.json").exists():
        previous_kg = load_json(previous_dir / "kg_prepared.json")
    if previous_dir and (previous_dir / "community_reports.json").exists():
        previous_reports = load_json(previous_dir / "community_reports.json")
    if previous_dir:
        log(f"      앞 결과 폴더: {previous_dir} (추출 결과 {'있음' if previous_kg else '없음'}, "
            f"보고서 {len(previous_reports)}개)")

    # ③ 인덱스 구축 — KG 구축(K1 ~ K6, K8). 전체 재색인은 새 세대에 쓰므로 검색엔진 쪽과 순서가 없음(여기서는 차례로 돌림)
    log("③ 인덱스 구축 시작: KG 구축(K1 ~ K6, K8) → 검색엔진 인덱싱(S1 ~ S3)")
    schemas = load_schemas()
    units, empty_chunks = core.k1_split_units(chunks, schemas)
    multi = [u for u in units if len(u["chunk_ids"]) > 1]
    by_type_units = {}
    for unit in units:
        by_type_units[unit["doc_type"]] = by_type_units.get(unit["doc_type"], 0) + 1
    log(f"[K1] 청크 {len(chunks)}개 → 추출 단위 {len(units)}개 {by_type_units}, 청크 2개 이상에 걸친 단위 {len(multi)}개, "
        f"단위가 없는 청크 {len(empty_chunks)}개 {[c[:22] for c in empty_chunks][:5]}")
    sample_unit = next((u for u in units if u["doc_type"] == "regulation"), units[0] if units else None)
    if sample_unit:
        log(f"      단위 예: {sample_unit['unit_id']} ← 청크 {sample_unit['chunk_ids']}, 본문 {len(sample_unit['text'])}자")

    k2 = k2_k3_extract(units, schemas, previous_kg)
    failed = [u for u in units if "error" in u]
    raw_nodes = sum(u.get("raw_nodes", 0) for u in units)
    kept_nodes = sum(len(u.get("graph", {}).get("nodes", [])) for u in units)
    log(f"[K3] 가지치기: 새로 추출한 단위의 노드 {raw_nodes}개 → 남은 노드(재사용 포함) {kept_nodes}개, "
        f"실패 단위 {len(failed)}개, 토큰 {k2['usage'].get('total_tokens', 0):,}")
    if failed:
        log(f"      첫 실패: {failed[0]['unit_id']} — {failed[0]['error'][:100]}")
    log(f"      머리줄 채움률(%): {header_fill_rate(units, schemas)}")
    shown = next((u for u in units if "graph" in u and u["graph"]["nodes"]), None)
    if shown:
        labels = [n["label"] for n in shown["graph"]["nodes"]][:8]
        rels = [r["type"] for r in shown["graph"]["relationships"]][:6]
        log(f"      단위 {shown['unit_id'][:40]}의 노드 {labels}, 관계 {rels}")
    kg_prepared = {"chunks": [{"chunk_id": c["chunk_id"], "doc_id": c["doc_id"], "doc_type": c["doc_type"]} for c in chunks],
                   "units": units, "no_unit_chunks": empty_chunks, "failed_units": [u["unit_id"] for u in failed],
                   "llm_usage": k2["usage"]}
    save_json(gen_dir / "kg_prepared.json", kg_prepared)  # 준비 결과 보관: 뒤에서 실패해도 LLM을 다시 부르지 않음

    nodes, relationships, merge_keys = core.build_graph_rows(chunks, units, schemas, generation, run_id)
    k4_write(driver, nodes, relationships)
    from_chunk = sum(1 for r in relationships if r.type == "FROM_CHUNK")
    log(f"[K4] 적재: 노드 {len(nodes)}개(청크 노드 {len(chunks)}개 포함), 관계 {len(relationships)}개"
        f"(FROM_CHUNK {from_chunk}, 추출 관계 {len(relationships) - from_chunk})")

    merged = core.k5_merge(driver, generation, merge_keys)
    removed = dedup_from_chunk(driver, generation)
    examples = sorted(merge_keys)[:3]
    log(f"[K5] 병합: 검사한 값 {len(merge_keys)}개 중 {merged}묶음 합침, FROM_CHUNK 중복 {removed}개 지움. 값 예: {examples}")

    embedded = core.k6_embed_descriptions(driver, generation, embed_texts, EMBED_DIMENSION, ENTITY_INDEX)
    records, _, _ = driver.execute_query(
        "MATCH (n:__Entity__ {generation: $g}) RETURN [l IN labels(n) WHERE NOT l STARTS WITH '__'][0] AS label, "
        "properties(n) AS props LIMIT 3", g=generation)
    log(f"[K6] 엔티티 설명 임베딩 {embedded}개({EMBED_DIMENSION}차원), 벡터 인덱스 {ENTITY_INDEX}")
    for record in records:
        log(f"      설명 글 예: {core.entity_description(record['label'], dict(record['props']))[:110]}")

    k8_result = None
    if communities:
        k8_result, reports = k8_summarize(driver, generation, run_id, previous_reports)
        save_json(gen_dir / "community_reports.json", reports)

    # ③ 인덱스 구축 — 검색엔진 인덱싱(S1 ~ S3)
    index = index_name(generation)
    old_vectors = read_old_vectors(os_client, active["search_index"] if active else None)
    texts = [c["text"] for c in chunks]
    hashes = [c["text_hash"] for c in chunks]
    vectors, new_count = core.embed_with_reuse(texts, hashes, old_vectors, embed_texts)
    log(f"[S1] 임베딩 {new_count}개 새로, {len(chunks) - new_count}개 재사용({EMBEDDING_MODEL}, {len(vectors[0])}차원). "
        f"벡터 앞 3개: {[round(v, 4) for v in vectors[0][:3]]}")

    lexicon = kr_tokenizer.lexicon_from_chunks(chunks, kr_tokenizer.load_approved_aliases(ALIASES_APPROVED_PATH))
    docs = core.build_search_docs(chunks, hashes, vectors, lexicon, META_FIELDS)
    alias_count = sum(len(v) for v in lexicon.aliases.values())
    log(f"[S2] 키워드 분석 {len(docs)}개 (카드명 사전 {len(lexicon.card_names)}개, 별칭 {alias_count}개). "
        f"예: {docs[0]['text_tokens'][:80]}")

    s3 = core.apply_search(os_client, index, docs, index_mapping(lexicon.meta()))
    log(f"[S3] 적재: 인덱스 {index}, 문서 {s3['documents']}개, 옛 청크 {s3['deleted']}건 지우고 {s3['indexed']}건 넣음")

    # ④ 검증
    all_ids = {c["chunk_id"] for c in chunks}
    search_ids = search_chunk_ids(os_client, index)
    kg_list = graph_chunk_ids(driver, generation)
    report = core.verify_chunk_ids(all_ids, search_ids, kg_list)
    report["failed_units"] = kg_prepared["failed_units"]  # 게시 조건은 아님. 엔티티가 빠진 청크를 알리는 기록
    log(f"④ 검증: {'통과' if report['ok'] else '실패'} (검색엔진 {len(search_ids)}/{len(all_ids)}, "
        f"KG 청크 노드 {len(kg_list)}개 = 고유 {len(set(kg_list))}/{len(all_ids)}, 중복 노드 {len(report['kg_duplicate_chunk_nodes'])}, "
        f"추출 실패 단위 {len(report['failed_units'])}개)")
    if communities:
        c = report["communities"] = verify_communities(driver, generation)
        report["ok"] = report["ok"] and c["ok"]
        log(f"④ 검증(K8): {'통과' if c['ok'] else '실패'} (커뮤니티 {c['communities']}개, 요약 빠짐 {c['incomplete']}, "
            f"빈 묶음 {c['empty']}, 세대 밖 구성원 {c['foreign_members']})")
    labels = label_counts(driver, generation)
    elapsed = round(time.time() - started)
    save_json(gen_dir / "build_report.json", {
        "run_id": run_id, "generation": generation, "chunks": len(chunks), "units": len(units),
        "k2": {k: v for k, v in k2.items()}, "k4": {"nodes": len(nodes), "relationships": len(relationships)},
        "k5_merged_groups": merged, "k6_embedded": embedded, "k8": k8_result,
        "s1_new_embeddings": new_count, "s3": s3, "verify": report, "labels": labels, "elapsed_seconds": elapsed})
    if not report["ok"]:
        raise SystemExit(f"④ 검증 실패: 게시하지 않음(활성 세대는 그대로). 자세한 목록: {gen_dir / 'build_report.json'}")

    # ⑤ 게시
    core.publish_active({
        "generation": generation, "search_index": index, "neo4j_generation": generation, "chunk_count": len(chunks),
        "input_sha256": input_sha256, "config_signature": config_signature(),
        "published_at": time.strftime("%Y-%m-%d %H:%M:%S"), "runs": [run_id]}, ACTIVE_FILE)
    log(f"⑤ 게시: 활성 세대 파일 → {generation}")

    log(f"완료: {elapsed}초. 엔티티 라벨별 {labels}")
    log(f"다음: ../.venv/Scripts/python.exe check_graph.py --qid Q02   (질문으로 검색엔진 → 청크 → 엔티티를 확인)")
    driver.close()


def main() -> None:
    """명령줄 인자를 읽어 run을 부름."""
    parser = argparse.ArgumentParser(description="GraphRAG 인덱싱 예제(전체 재색인)")
    parser.add_argument("--run", required=True, help="실행 이름. 교육생 별명을 넣음(예: hong-s1). 같은 이름이면 같은 세대 ID")
    parser.add_argument("--sample", action="store_true", help="표본 10청크만(수업용)")
    parser.add_argument("--full-reindex", action="store_true", help="사전 검사를 건너뛰고 새 세대를 만듦")
    parser.add_argument("--skip-communities", action="store_true", help="K8 커뮤니티 요약을 건너뜀")
    parser.add_argument("--reuse", default=None, help="앞 결과 폴더(kg_prepared.json, community_reports.json). 강사 배포본 등")
    parser.add_argument("--chunks", default=None, help="Chroma 대신 쓸 청크 파일(prepared-chunks.json)")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
