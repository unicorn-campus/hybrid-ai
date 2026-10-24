"""1단계와 3단계 분석: 청크 위치 파일 해석, 청크 구조와 문서 종류, 개인정보 점검, 메타데이터 필드 분포(묶음 기준 제안 근거).

실행: python tools/prepare.py {청크 파일 또는 청크 위치 파일} → output/input_scan.json
값(개인정보)은 저장하지 않고 건수와 위치만 남김.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PII = {
    "전화번호": re.compile(r"(?<!\d)01[016789][ -]?\d{3,4}[ -]?\d{4}(?!\d)"),
    "이메일": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "카드나 계좌 번호": re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)"),
    "주민번호": re.compile(r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)"),
    "생년월일": re.compile(r"(?:생일|생년월일|출생)\s*(?:은|는|이|:)?\s*\d{4}\s*(?:년|[.-])\s*\d{1,2}\s*(?:월|[.-])\s*\d{1,2}"),
}


def resolve(path: Path) -> tuple[Path, list[str]]:
    """청크 파일이면 그대로, 위치를 가리키는 파일이면 근거와 함께 실제 청크 파일을 찾음."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list) or any(isinstance(v, list) and v and isinstance(v[0], dict) and "metadata" in v[0]
                                     for v in data.values()):
        return path, ["받은 파일이 청크 목록임"]
    reasons = []
    gen = str(data.get("generation", ""))
    count = data.get("chunk_count")
    root = path.parent
    cands = sorted(root.rglob("prepared-chunks.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    reasons.append(f"위치 파일에 청크 경로는 없음. generation={gen}, chunk_count={count}")
    best = None
    for c in cands:
        run_id = c.parent.name
        name_ok = bool(gen) and gen.startswith(f"gen-{run_id}-")
        rows = json.loads(c.read_text(encoding="utf-8"))
        rows = rows if isinstance(rows, list) else next(v for v in rows.values() if isinstance(v, list))
        count_ok = count is None or len(rows) == count
        if name_ok and count_ok:
            best = c
            reasons.append(f"이름 규칙 일치: gen-{{실행 ID}}-{{해시}}의 실행 ID = 산출물 폴더 '{run_id}'")
            reasons.append(f"청크 수 일치: {len(rows)}개")
            break
    if best is None:
        raise SystemExit("청크 파일을 확정하지 못함 → 사용자에게 고르게 해야 함")
    return best, reasons


def main() -> None:
    src = Path(sys.argv[1])
    chunk_file, reasons = resolve(src)
    data = json.loads(chunk_file.read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    fields = sorted(rows[0].keys())
    md_keys = Counter(k for r in rows for k in r.get("metadata", {}))
    doc_types = Counter(r["metadata"].get("doc_type") for r in rows)
    pii = {name: [r.get("chunk_id") for r in rows if pat.search(r.get("text", ""))] for name, pat in PII.items()}
    # 문서 종류마다 메타데이터 필드의 값 수와 값별 청크 수(묶음 기준 후보 판단용)
    dist = defaultdict(dict)
    for dt in doc_types:
        sub = [r for r in rows if r["metadata"].get("doc_type") == dt]
        for k in sorted({k for r in sub for k in r["metadata"]}):
            vals = Counter(str(r["metadata"].get(k)) for r in sub)
            dist[dt][k] = {"distinct": len(vals), "top": vals.most_common(8)}
    out = {"source_file": str(src), "chunk_file": str(chunk_file), "resolve_reasons": reasons,
           "chunk_count": len(rows), "chunk_fields": fields, "metadata_fields": dict(md_keys),
           "doc_types": dict(doc_types), "pii_found": {k: {"count": len(v), "chunk_ids": v[:5]} for k, v in pii.items()},
           "metadata_distribution": dist}
    (BASE / "output").mkdir(exist_ok=True)
    (BASE / "output/input_scan.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in ("chunk_file", "resolve_reasons", "chunk_count", "chunk_fields", "doc_types",
                                          "pii_found")}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
