"""S2 키워드 분석에 쓰는 한국어 토크나이저와 카드 별칭 규칙.

출처: hands-on/solutions/rag/indexing/core_indexing.py의 canonical_card_name, _is_common_noun, make_alias_table,
build_alias_lookup, build_tokenizer, apply_aliases, tokenize_korean을 그대로 옮김(2026-10-24). 이 저장소 RAG 검색기와
같은 규칙으로 잘라야 같은 질문이 같은 토큰이 됨. core_indexing.py를 import하지 않는 것은 그 파일이 bm25s, chromadb,
langchain을 맨 위에서 불러 v0 가상환경에 필요 없는 패키지가 따라오기 때문임.
사람 검수를 통과한 별칭은 hands-on/solutions/rag/indexing/aliases_approved.json(강사 제공)을 읽기만 함.

v0에서 더한 것: Lexicon(사전 기록으로 같은 토크나이저를 다시 만드는 묶음)과 서명(signature).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from kiwipiepy import Kiwi

from common import sha256_text

CONTENT_TAGS = {"NNG", "NNP", "NR", "SN", "SL", "VV", "VA"}  # 색인에 남기는 내용어 품사
CODE_PATTERN = re.compile(r"[A-Za-z]+\d*-[A-Za-z]*\d+(?:-[A-Za-z]*\d+)*")  # D2-C001 꼴 코드
NUMBER_COMMA_PATTERN = re.compile(r"(?<=\d),(?=\d)")  # "3,000,000" 안의 쉼표
CARD_NAME_PREFIX = "한빛 "  # 카드명 앞의 회사명
CARD_WORD = "카드"  # 별칭에 붙이는 말
ALIAS_MIN_LENGTH = 3  # 두 글자 이하 별칭은 걸러냄


# ---------------------------------------------------------------- core_indexing.py에서 옮긴 함수

def canonical_card_name(card_name: str) -> str:
    """카드명을 정식명 토큰으로 바꿈. 예: "한빛 모아생활" → "한빛모아생활"."""

    name = card_name.strip().lower()
    if name.endswith(CARD_WORD):
        name = name[: -len(CARD_WORD)]
    return name.replace(" ", "")


def _is_common_noun(base_kiwi: Kiwi, alias: str) -> bool:
    """별칭이 Kiwi 기본 사전에 형태소 1개짜리 일반명사(NNG)로 있으면 겹침으로 봄."""

    core = alias.replace(" ", "")
    if core.endswith(CARD_WORD):
        core = core[: -len(CARD_WORD)]
    tokens = list(base_kiwi.tokenize(core))
    return len(tokens) == 1 and tokens[0].tag == "NNG"


def make_alias_table(card_names: list[str], approved: dict | None = None) -> tuple[dict, list[dict]]:
    """정식명 목록에서 별칭 후보를 규칙으로 만들고 위험한 후보를 걸러 별칭 사전을 만듦.

    후보 = {원래 이름, 접두어 뗀 이름, 띄어쓰기 없앤 이름} × {그대로, "카드" 붙임, " 카드" 붙임}.
    걸러내기: ① 일반 명사와 겹침 ② 정식명 여러 개를 가리킴 ③ 두 글자 이하. approved(사람 승인분)는 걸러내기와 무관하게 더함.
    반환값: (별칭 사전 {정식명: [별칭, ...]}, 검수 목록 [{"alias", "canonical", "reason"}, ...]).
    """

    base_kiwi = Kiwi()
    candidates: dict[str, set] = {}
    for card_name in card_names:
        canonical = canonical_card_name(card_name)
        full_name = card_name.strip().lower()
        short_name = full_name[len(CARD_NAME_PREFIX):] if full_name.startswith(CARD_NAME_PREFIX) else full_name
        forms = set()
        for form in {full_name, short_name, short_name.replace(" ", "")}:
            forms.update({form, form + CARD_WORD, form + " " + CARD_WORD})
        forms.discard(canonical)
        for alias in forms:
            candidates.setdefault(alias, set()).add(canonical)

    aliases: dict[str, list[str]] = {}
    review = []
    for alias in sorted(candidates):
        canonicals = candidates[alias]
        reason = None
        if len(canonicals) > 1:
            reason = "정식명 여러 개를 가리킴"
        elif len(alias.replace(" ", "")) < ALIAS_MIN_LENGTH:
            reason = "두 글자 이하"
        elif _is_common_noun(base_kiwi, alias):
            reason = "일반 명사와 겹침"
        if reason is not None:
            review.append({"alias": alias, "canonical": sorted(canonicals)[0], "reason": reason})
            continue
        aliases.setdefault(sorted(canonicals)[0], []).append(alias)

    approved_set = set()
    for canonical, extra_aliases in (approved or {}).items():
        slot = aliases.setdefault(canonical, [])
        for alias in extra_aliases:
            alias = alias.strip().lower()
            approved_set.add(alias)
            if alias not in slot:
                slot.append(alias)
    return aliases, [item for item in review if item["alias"] not in approved_set]


def build_alias_lookup(aliases: dict) -> dict:
    """별칭 사전을 뒤집어 {별칭: 정식명}을 만듦. 정식명 자신도 넣음."""

    alias_to_name = {}
    for canonical, alias_list in aliases.items():
        alias_to_name[canonical] = canonical
        for alias in alias_list:
            alias_to_name[alias] = canonical
    return alias_to_name


def build_tokenizer(card_names: list[str], aliases: dict) -> Kiwi:
    """Kiwi에 카드명 원문(소문자), 정식명, 모든 별칭을 고유명사(NNP)로 등록함."""

    kiwi = Kiwi()
    for card_name in card_names:
        kiwi.add_user_word(card_name.strip().lower(), "NNP")
        kiwi.add_user_word(canonical_card_name(card_name), "NNP")
    for alias_list in aliases.values():
        for alias in alias_list:
            kiwi.add_user_word(alias, "NNP")
    return kiwi


def apply_aliases(tokens: list[str], alias_to_name: dict) -> list[str]:
    """별칭을 정식명으로 바꾸고, 같은 정식명은 호출 하나 안에서 1개만 남김. 다른 토큰은 그대로 둠."""

    result, seen_names = [], set()
    for token in tokens:
        if token not in alias_to_name:
            result.append(token)
            continue
        canonical = alias_to_name[token]
        if canonical in seen_names:
            continue
        seen_names.add(canonical)
        result.append(canonical)
    return result


def tokenize_korean(kiwi: Kiwi, text: str, alias_to_name: dict) -> list[str]:
    """① 숫자 쉼표 제거와 소문자화 ② 코드(D2-C001 꼴) 통째로 추가 ③ Kiwi 내용어만 남김 ④ 별칭 치환.

    불규칙 활용 태그(VV-I, VA-I 등)는 "-" 앞부분으로 비교함.
    """

    normalized = NUMBER_COMMA_PATTERN.sub("", text).lower()
    tokens = list(CODE_PATTERN.findall(normalized))
    for token in kiwi.tokenize(normalized):
        if token.tag.split("-")[0] in CONTENT_TAGS:
            tokens.append(token.form)
    return apply_aliases(tokens, alias_to_name)


# ---------------------------------------------------------------- v0에서 더한 것

def load_approved_aliases(path: Path) -> dict:
    """사람 검수를 통과한 별칭 파일을 읽음. "_"로 시작하는 설명 키는 뺌. 파일이 없으면 빈 dict."""

    if not Path(path).is_file():
        return {}
    approved = json.loads(Path(path).read_text(encoding="utf-8"))
    return {k: v for k, v in approved.items() if not k.startswith("_")}


class Lexicon:
    """카드명 목록과 별칭 사전으로 만든 토크나이저 묶음. 사전 기록(meta)만 있으면 색인 쪽과 질문 쪽이 같은 것을 다시 만듦."""

    def __init__(self, card_names: list[str], aliases: dict) -> None:
        self.card_names = sorted(set(card_names))
        self.aliases = {k: sorted(v) for k, v in sorted(aliases.items())}
        self.kiwi = build_tokenizer(self.card_names, self.aliases)
        self.alias_to_name = build_alias_lookup(self.aliases)
        self.signature = sha256_text(json.dumps([self.card_names, self.aliases], ensure_ascii=False))

    def tokenize_many(self, texts: list[str]) -> list[list[str]]:
        return [tokenize_korean(self.kiwi, t, self.alias_to_name) for t in texts]

    def meta(self) -> dict:
        return {"card_names": self.card_names, "aliases": self.aliases, "lexical_signature": self.signature}


def lexicon_from_chunks(chunks: list[dict], approved: dict) -> Lexicon:
    """혜택 안내 청크의 카드명으로 별칭 사전을 만들어 Lexicon을 돌려줌(core_indexing.py 단계 7과 같은 규칙)."""

    names = {str(c["metadata"]["card_name"]).strip() for c in chunks
             if c["metadata"].get("doc_type") == "benefit_guide" and c["metadata"].get("card_name")}
    aliases, _review = make_alias_table(sorted(names), approved)
    return Lexicon(sorted(names), aliases)


def lexicon_from_meta(meta: dict) -> Lexicon:
    """기록된 사전으로 같은 Lexicon을 다시 만듦. 서명이 기록과 다르면 ValueError."""

    if "card_names" not in meta:
        raise ValueError("옛 사전 기록 꼴(hybrid-ai-lab 1-a 토크나이저)임: 새 실행 이름으로 full을 다시 돌려야 함")
    lex = Lexicon(meta["card_names"], meta["aliases"])
    if lex.signature != meta["lexical_signature"]:
        raise ValueError("다시 만든 토크나이저 서명이 기록과 다름")
    return lex
