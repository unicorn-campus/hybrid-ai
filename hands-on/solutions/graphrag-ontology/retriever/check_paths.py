"""건너가는 지점(P1 ~ P6) 점검: 에이전트 없이 검색기의 경로 함수를 활성 세대에 직접 불러 결과를 찍음.

LLM을 부르지 않음(임베딩은 E3 후보가 필요할 때만 Cohere를 부름). 정형 조회는 SQL을 직접 줘서 실행함.
실행(이 폴더에서): ../../graphrag/.venv/Scripts/python.exe check_paths.py --member-id M-1001
"""

import argparse

import core_search as core
import core_sql
import search_graph as sg


def show(title: str, rows: list[dict]) -> None:
    """엔티티 목록을 한 줄씩 찍음."""
    sg.say(f"\n[{title}] {len(rows)}개")
    for row in rows[:10]:
        sg.say(f"  - {sg.short(sg.entity_text(row['label'], dict(row['props'])), 110)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="건너가는 지점 P1 ~ P6 점검")
    parser.add_argument("--member-id", default="M-1001", help="회원번호(정형 DB와 상담 기록에 모두 있는 회원)")
    args = parser.parse_args()

    res = sg.Resources()
    data = sg.start_check(res)
    sg.RES = res
    sg.DATA.update(data)
    pseudo = core.member_pseudonym(args.member_id)
    filters = {"generation": res.active["generation"], "index": res.active["search_index"],
               "allowed_ids": core.allowed_chunk_ids(data["chunk_meta"], "auditor", pseudo, []),
               "allowed_reports": set(data["reports"]), "member_pseudo_id": pseudo, "member_id": args.member_id,
               "card_ids": [], "question_vector": None}
    ctx = {"calls": {"cohere": 0}, "warnings": []}
    sg.say(f"세대 {res.active['generation']}, 회원 {args.member_id} → 가명 키 {pseudo}(P5 바꾸는 규칙)")
    sg.say(f"공통 개념 층 Class {len(data['concept_names'])}개, 뷰 설명 {list(data['schema']['views'])}, "
           f"건너가는 키 컬럼 {data['schema']['key_columns']}")

    members = sg.find_entities(res, "회원", filters, ctx)  # P5
    show("P5 회원 → 가명 키 → 상담", members["entities"])

    consult_ids = [e["id"] for e in members["entities"] if e["label"] == "Consultation"]
    p3 = sg.follow_crossing(res, "P3", consult_ids, filters)  # P3
    sg.say(f"\n[P3 상담 → product_id → 혜택, 이용 기준] 경로 {len(p3['rows'])}개, 도착 있는 경로 {p3['linked']}개")
    for row in p3["rows"]:
        sg.say(f"  - {row['start']['props'].get('record_id')} product_id={row['start']['props'].get('product_id')} → "
               + ", ".join(t["props"].get("benefit_id") or t["props"].get("item_id") or "?" for t in row["targets"]))

    for point in ("P1", "P2"):  # P1, P2: 출발 id 없이 볼 수 있는 모든 불만에서
        found = sg.follow_crossing(res, point, [], filters)
        sg.say(f"\n[{point} {core.CROSSING_POINTS[point]}] 경로 {len(found['rows'])}개, 도착 있는 경로 {found['linked']}개")
        for row in found["rows"]:
            sg.say(f"  - [{row['segment']}] {sg.short(row['complaint']['props'].get('content'), 40)} → 주제 "
                   f"{row['topic']['props'].get('name')} → "
                   + (", ".join(t["props"].get("article_no") or t["props"].get("benefit_id") or "?" for t in row["targets"])
                      or "(이어진 것 없음)"))

    sql_scope = data.get("sql_scope")
    if not sql_scope:
        sg.say("\n정형 DB에 접속하지 못해 P4, P6 점검을 건너뜀")
        return
    views = set(data["schema"]["views"])
    for point, question_sql, concept in (
            ("P6", "SELECT product_id, product_name FROM customer_cards ORDER BY product_id", "카드상품"),
            ("P4", "SELECT category, sum(approved_amount) AS amount FROM merchant_usage GROUP BY category "
                   "ORDER BY amount DESC", "업종")):
        sql = core_sql.check_sql(question_sql, views)
        rows = core_sql.run_sql(res.rdb_dsn, res.rdb_password, sql, args.member_id, sql_scope)
        keys = core_sql.bridge_keys(rows, data["schema"]["key_columns"]).get(concept, [])
        sg.say(f"\n[{point} 정형 DB → 건너갈 키({concept})] 조회 {len(rows)}행, 키 {keys}")
        for value in keys:
            found = sg.find_entities(res, f"{concept}:{value}", filters, ctx)
            kind = "키로 찾음" if found["entities"] else "키로 찾은 것 없음(아래는 E3 임베딩 후보)"
            show(f"{point} {concept}:{value} → {kind}", found["entities"] or found["candidates"])
    res.driver.close()


if __name__ == "__main__":
    main()
