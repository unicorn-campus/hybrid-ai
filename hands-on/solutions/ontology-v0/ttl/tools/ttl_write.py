"""온톨로지 원본(Turtle)을 쓰는 함수 모음. 스키마 설계 도구만 부름(인덱서와 검색기는 읽기만 함).

- 경로: 승인본 폴더(ttl/)와 초안 폴더(schema/doc-ontology/draft-ttl/). 초안이 있으면 설계 도구는 초안을 읽고 씀
- 저장: 파일 맨 위의 설명 주석을 지키고, 같은 내용이면 같은 글이 나오게 씀(이름 없는 노드 대신 이름 있는 주소를 씀)
- 맞추기 표: 설계 도구가 쓰는 행 목록(이름, 대표 이름, 상태)과 Turtle 사이를 오감
"""
import re
import sys
from pathlib import Path

from rdflib import Graph, Literal
from rdflib.namespace import DCTERMS, OWL, RDF, RDFS, SKOS, XSD

TTL_DIR = Path(__file__).resolve().parents[1]  # 승인본
PROJECT = TTL_DIR.parent
BASE_DIR = PROJECT / "schema" / "doc-ontology"  # 스키마 설계의 출력 기준 폴더
DRAFT_DIR = BASE_DIR / "draft-ttl"  # 초안. 사람이 승인하면 승인본으로 올림(tools/draft.py promote)
sys.path.insert(0, str(PROJECT / "indexer"))
import core_turtle as turtle  # noqa: E402
from core_turtle import CARD, SH  # noqa: E402

PREFIXES = {"card": CARD, "dcterms": DCTERMS, "owl": OWL, "rdf": RDF, "rdfs": RDFS, "sh": SH, "skos": SKOS, "xsd": XSD}
FILES = ["card.ttl", "shapes/regulation.ttl", "shapes/benefit_guide.ttl", "shapes/consult_log.ttl", "shapes/checks.ttl",
         "maps/topic.ttl", "maps/category.ttl"]
TOPIC_HEADER = """# 주제 맞추기 표(원본). LLM이 지은 주제 이름을 대표 이름 하나로 모음.
#   skos:prefLabel  대표 이름. skos:altLabel  같은 주제로 확정한 다른 이름
#   card:PendingMapping  아직 확정하지 않은 이름(status가 needs_review) 또는 잇지 않기로 한 이름(not_linked). 인덱서는 확정한 것만 바꿈"""
CATEGORY_HEADER = """# 업종 맞추기 표(원본). 혜택의 대상 문장을 업종 값 8개 중 하나에 맞춤. LLM이 후보를 내고 사람이 확정함.
#   card:IN_CATEGORY     확정한 업종(값은 card.ttl의 업종 값 목록). 인덱서가 이 행만 그래프에 이음
#   card:PendingMapping  잇지 않기로 했거나 아직 정하지 않은 혜택(status), card:near는 가까운 후보
#   rdfs:label 혜택 이름, card:target 대상 문장, skos:note 고른 까닭"""


def work_dir() -> Path:
    """설계 도구가 읽고 쓸 폴더: 초안이 있으면 초안, 없으면 승인본."""
    return DRAFT_DIR if DRAFT_DIR.exists() else TTL_DIR


def header_of(path: Path) -> str:
    """파일 맨 위에 이어진 주석 줄(설명)을 돌려줌. 다시 저장할 때 그대로 붙임."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            break
        lines.append(line)
    return "\n".join(lines)


def save(graph: Graph, path: Path, header: str) -> None:
    """그래프를 Turtle로 저장함. 접두어를 묶고, 맨 위에 설명 주석을 붙임."""
    for prefix, namespace in PREFIXES.items():
        graph.bind(prefix, namespace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header.strip() + "\n\n" + graph.serialize(format="turtle"), encoding="utf-8", newline="\n")


def slug(text: str) -> str:
    return re.sub(r"\s+", "_", str(text).strip())


# ---------------------------------------------------------------------------
# 주제 맞추기 표
# ---------------------------------------------------------------------------
def topic_rows(ttl_dir: Path) -> list[dict]:
    """주제 맞추기 표를 행 목록으로 읽음: name, representative(대표 이름 또는 None), status."""
    g = turtle.read(ttl_dir / "maps" / "topic.ttl")
    rows = {}
    for topic in g.subjects(RDF.type, SKOS.Concept):
        representative = str(g.value(topic, SKOS.prefLabel))
        for name in [representative] + [str(o) for o in g.objects(topic, SKOS.altLabel)]:
            rows[name] = {"name": name, "representative": representative, "status": "approved"}
    for row in g.subjects(RDF.type, CARD.PendingMapping):
        proposed = g.value(row, CARD.proposed)
        name = str(g.value(row, CARD.name))
        rows[name] = {"name": name, "status": str(g.value(row, CARD.status)),
                      "representative": None if proposed is None or str(proposed) == "None" else str(proposed)}
    return [rows[name] for name in sorted(rows)]


def write_topic_rows(rows: list[dict], decided_by: str, date: str, ttl_dir: Path) -> None:
    """행 목록을 주제 맞추기 표로 씀. approved 행은 대표 이름 아래에 모으고, 나머지는 확정 전 행으로 적음."""
    g = Graph()
    g.add((CARD.topicMap, RDF.type, OWL.Ontology))
    g.add((CARD.topicMap, DCTERMS.creator, Literal(decided_by)))
    g.add((CARD.topicMap, DCTERMS.dateAccepted, Literal(date)))
    for row in rows:
        if row["status"] == "approved" and row.get("representative"):
            node = CARD["topic_" + slug(row["representative"])]
            g.add((node, RDF.type, SKOS.Concept))
            g.add((node, SKOS.prefLabel, Literal(row["representative"])))
            if row["name"] != row["representative"]:
                g.add((node, SKOS.altLabel, Literal(row["name"])))
        else:
            node = CARD["pending_topic_" + slug(row["name"])]
            g.add((node, RDF.type, CARD.PendingMapping))
            g.add((node, CARD.name, Literal(row["name"])))
            g.add((node, CARD.status, Literal(row["status"])))
            if row.get("representative"):
                g.add((node, CARD.proposed, Literal(row["representative"])))
    save(g, ttl_dir / "maps" / "topic.ttl", TOPIC_HEADER)


# ---------------------------------------------------------------------------
# 업종 맞추기 표
# ---------------------------------------------------------------------------
def category_values(ttl_dir: Path) -> dict:
    """업종 값 이름 → card.ttl의 값 주소."""
    card = turtle.read(ttl_dir / "card.ttl")
    return {str(card.value(v, SKOS.prefLabel)): v for v in card.subjects(RDF.type, CARD.Category)}


def category_rows(ttl_dir: Path) -> list[dict]:
    """업종 맞추기 표를 행 목록으로 읽음: benefit_id, name, target, category(확정한 업종 또는 None), reason, near, status."""
    g = turtle.read(ttl_dir / "maps" / "category.ttl")
    names = {v: k for k, v in category_values(ttl_dir).items()}
    rows = []
    for subject in set(g.subjects(CARD.benefit_id, None)):
        category = g.value(subject, CARD.IN_CATEGORY)
        status = g.value(subject, CARD.status)
        rows.append({"benefit_id": str(g.value(subject, CARD.benefit_id)), "name": str(g.value(subject, RDFS.label) or ""),
                     "target": str(g.value(subject, CARD.target) or ""), "category": names.get(category),
                     "reason": str(g.value(subject, SKOS.note) or ""), "near": sorted(str(o) for o in g.objects(subject, CARD.near)),
                     "status": "approved" if category is not None else str(status)})
    return sorted(rows, key=lambda r: r["benefit_id"])


def write_category_rows(rows: list[dict], decided_by: str, date: str, ttl_dir: Path) -> None:
    """행 목록을 업종 맞추기 표로 씀. approved 행만 IN_CATEGORY로 잇고, 나머지는 확정 전 행으로 적음."""
    values = category_values(ttl_dir)
    g = Graph()
    g.add((CARD.categoryMap, RDF.type, OWL.Ontology))
    g.add((CARD.categoryMap, DCTERMS.creator, Literal(decided_by)))
    g.add((CARD.categoryMap, DCTERMS.dateAccepted, Literal(date)))
    for row in rows:
        approved = row["status"] == "approved" and row.get("category") in values
        node = CARD[("benefit_" if approved else "pending_benefit_") + row["benefit_id"]]
        g.add((node, CARD.benefit_id, Literal(row["benefit_id"])))
        g.add((node, RDFS.label, Literal(row.get("name") or "")))
        g.add((node, CARD.target, Literal(row.get("target") or "")))
        if row.get("reason"):
            g.add((node, SKOS.note, Literal(row["reason"])))
        if approved:
            g.add((node, CARD.IN_CATEGORY, values[row["category"]]))
        else:
            g.add((node, RDF.type, CARD.PendingMapping))
            g.add((node, CARD.status, Literal(row["status"])))
            for near in row.get("near") or []:
                g.add((node, CARD.near, Literal(near)))
    save(g, ttl_dir / "maps" / "category.ttl", CATEGORY_HEADER)
