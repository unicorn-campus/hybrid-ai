"""주제 하나를 받아 리서치 → 기획 → 집필 → 검토·수정 → 슬라이드 → 과정 검토 → 발행까지
스스로 진행하고, 그 실행 기록으로 자기 하네스를 고치는(RSI) 교재 제작 에이전트."""
from __future__ import annotations

import json
import logging
import re
import shutil
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

import anyio

from . import prompts as P
from .config import Settings
from .harness import CONFIG_BOUNDS, Harness, _describe
from .lint import lint_chapter
from .llm import ask, ledger
from .pptx_builder import _text_fields, build_deck, lint_spec, spec_to_markdown
from .render import render_index_html
from .state import State

log = logging.getLogger("courseware")


class CoursewareAgent:
    def __init__(self, settings: Settings, harness: Harness, notifier=None) -> None:
        self.s = settings
        self.h = harness
        self.notifier = notifier      # 작업 변경 요약 메일(데몬에서만 연결)
        self.h.apply_config(self.s)
        self.s.ensure_dirs()
        self.state = State(settings.state_path)
        self.state.data["topic"] = settings.topic
        self._loops_since_improve = 0
        self._improve_lock = anyio.Lock()

    # ============================================================ 전체 루프

    async def run(self) -> None:
        log.info("주제 '%s' 교재 제작 시작 (출력: %s, 하네스 v%d %s)",
                 self.s.topic, self.s.out_dir, self.h.version, self.h.status)
        await self.research()
        await self.plan()
        await self.produce_all()
        if self.s.text_only:
            self.publish()
            log.info("본문만 완료(--text-only): LLM 호출 %d회", ledger.calls)
            return

        applied = False
        for round_no in range(len(self.state.data["course_reviews"]), self.s.max_course_reviews):
            applied = await self.course_review(round_no, apply=True)
            if not applied:
                break
            await self.produce_all()
        if applied or not self.state.data["course_reviews"]:
            await self.course_review(len(self.state.data["course_reviews"]), apply=False)

        self.publish()
        await self.improve("교재 1회 완성")
        log.info("완료: LLM 호출 %d회, 보고된 비용 $%.2f", ledger.calls, ledger.cost_usd)

    async def _notify(self, kind: str, message: str, urgent: bool = False) -> None:
        """작업 변경 이벤트를 메일 대기열에 넣고, 보낼 때가 됐으면 보낸다."""
        if self.notifier is None:
            return
        self.notifier.event(self.s.topic, kind, message, urgent)
        try:
            await anyio.to_thread.run_sync(self.notifier.flush)
        except Exception as err:   # 메일 실패가 제작을 멈추지 않게 한다
            log.warning("메일 처리 실패: %s", err)

    def is_complete(self) -> bool:
        plan = self.state.data.get("plan")
        if not plan or not self.state.data["course_reviews"]:
            return False
        return all(self.state.chapter(c["id"])["slide_status"] == "rendered" for c in plan["chapters"])

    # ============================================================ 1. 리서치

    async def research(self) -> None:
        brief_path = self.s.research_dir / "brief.md"
        if self.state.data["research"] and brief_path.exists():
            log.info("리서치: 기존 결과 재사용")
            return
        log.info("리서치: 웹 자료 조사 중")
        res = await ask(
            self.s, P.research_prompt(self.s), system=P.research_system(self.s),
            schema=P.RESEARCH_SCHEMA, tools=["WebSearch", "WebFetch"], max_turns=80, label="research",
        )
        data = res.data
        checked = await anyio.to_thread.run_sync(_check_urls, [src["url"] for src in data["sources"]])
        alive = [src for src in data["sources"] if checked.get(src["url"], False)]
        dropped = [src["url"] for src in data["sources"] if src not in alive]
        if dropped:
            log.warning("리서치: 접속되지 않는 출처 %d개 제외 %s", len(dropped), dropped)
        data["sources"] = alive

        (self.s.research_dir / "sources.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        brief_path.write_text(_brief_markdown(self.s.topic, data), encoding="utf-8")
        self.state.data["research"] = {
            "brief_path": str(brief_path.relative_to(self.s.out_dir)),
            "sources": [src["url"] for src in alive],
            "concepts": [c["term"] for c in data["key_concepts"]],
            "dropped_sources": dropped,
        }
        self.state.event(f"리서치 완료: 출처 {len(alive)}개, 개념 {len(data['key_concepts'])}개")
        self.state.save()
        await self._notify("리서치", f"웹 자료 조사 완료(출처 {len(alive)}개, 핵심 개념 {len(data['key_concepts'])}개)")

    @property
    def brief(self) -> str:
        return (self.s.research_dir / "brief.md").read_text(encoding="utf-8")

    @property
    def source_urls(self) -> list[str]:
        return self.state.data["research"]["sources"]

    # ============================================================ 2. 기획

    async def plan(self) -> None:
        if self.state.data["plan"]:
            log.info("기획: 기존 커리큘럼 재사용 (%d장)", len(self.state.data["plan"]["chapters"]))
            return
        feedback = ""
        plan = None
        for attempt in range(3):
            log.info("기획: 커리큘럼 설계 (시도 %d)", attempt + 1)
            res = await ask(
                self.s, P.planner_prompt(self.s, self.brief, feedback),
                system=self.h.system("planner", P.planner_system(self.s)),
                schema=P.PLAN_SCHEMA, label="plan",
            )
            plan = res.data
            problems = self._validate_plan(plan)
            if not problems:
                break
            feedback = "\n".join(f"- {p}" for p in problems)
            log.warning("기획안 점검 실패:\n%s", feedback)
        self._normalize_plan(plan)
        self.state.data["plan"] = plan
        self.state.event(f"기획 완료: {len(plan['chapters'])}장")
        self.state.save()
        (self.s.out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        await self._notify("기획", f"커리큘럼 {len(plan['chapters'])}장 설계: "
                           + ", ".join(f"{c['id']} {c['title']}" for c in plan["chapters"]))

    def _validate_plan(self, plan: dict) -> list[str]:
        problems = []
        chapters = plan["chapters"]
        if not self.s.min_chapters <= len(chapters) <= self.s.max_chapters:
            problems.append(f"장 수 {len(chapters)}개 (허용 {self.s.min_chapters}~{self.s.max_chapters})")
        ids = [c["id"] for c in chapters]
        if len(set(ids)) != len(ids):
            problems.append("장 id 중복")
        for c in chapters:
            if not 3 <= len(c["objectives"]) <= 5:
                problems.append(f"{c['id']} 학습 목표 {len(c['objectives'])}개 (3~5개)")
            if not c["hands_on"].strip():
                problems.append(f"{c['id']} 실습 없음")
        return problems

    def _normalize_plan(self, plan: dict) -> None:
        for no, c in enumerate(plan["chapters"], 1):
            c["id"] = f"ch{no:02d}"
            c["slide_count"] = max(8, min(18, int(c.get("slide_count") or 12)))

    # ============================================================ 3. 장별 제작

    async def produce_all(self) -> None:
        chapters = self.state.data["plan"]["chapters"]
        for pass_no in range(2):
            todo = [c for c in chapters if not self._chapter_done(c["id"])]
            if not todo:
                return
            log.info("제작: %d개 장 진행 (동시 %d)", len(todo), self.s.concurrency)
            limiter = anyio.CapacityLimiter(self.s.concurrency)
            failures: list[str] = []

            async def worker(ch: dict) -> None:
                async with limiter:
                    try:
                        await self.produce_chapter(ch)
                    except Exception as err:  # 한 장의 실패가 다른 장을 멈추지 않게 한다
                        log.exception("%s 제작 실패", ch["id"])
                        failures.append(f"{ch['id']}: {err}")
                        await self._notify("오류", f"{ch['id']} 제작 실패: {str(err)[:200]}", urgent=True)

            async with anyio.create_task_group() as tg:
                for ch in todo:
                    tg.start_soon(worker, ch)
            if not failures:
                return
            self.state.event(f"제작 실패 {len(failures)}건, 재시도 {pass_no + 1}: {failures}")
            self.state.save()

    def _chapter_done(self, cid: str) -> bool:
        cs = self.state.chapter(cid)
        if self.s.text_only:
            return cs["text_status"] == "approved"
        return cs["slide_status"] == "rendered"

    def _chapter_no(self, cid: str) -> int:
        return [c["id"] for c in self.state.data["plan"]["chapters"]].index(cid) + 1

    def _paths(self, ch: dict) -> dict[str, Path]:
        stem = ch["id"]   # 파일 이름은 영문 id 만 쓰고, 장 제목은 문서 안에 둔다
        return {
            "text": self.s.textbook_dir / f"{stem}.md",
            "spec": self.s.slides_dir / f"{stem}.slides.json",
            "spec_md": self.s.slides_dir / f"{stem}.slides.md",
            "pptx": self.s.slides_dir / f"{stem}.pptx",
            "pdf": self.s.slides_dir / f"{stem}.pdf",
            "preview": self.s.slides_dir / "preview" / ch["id"],
        }

    def _deck_title(self, ch: dict) -> str:
        return f"{self._chapter_no(ch['id'])}장. {ch['title']}"

    async def produce_chapter(self, ch: dict) -> None:
        cs = self.state.chapter(ch["id"])
        paths = self._paths(ch)
        cs["files"] = {k: str(v.relative_to(self.s.out_dir)) for k, v in paths.items()}

        if cs["text_status"] == "pending" or not paths["text"].exists():
            await self._draft_text(ch, paths)
            cs["text_status"] = "drafted"
            await self._save()
        if cs["text_status"] == "drafted":
            await self._review_loop(ch, cs, paths, kind="text")
        if self.s.text_only:
            return

        if cs["slide_status"] == "pending" or not paths["spec"].exists():
            await self._draft_slides(ch, paths)
            cs["slide_status"] = "drafted"
            await self._save()
        if cs["slide_status"] in ("drafted", "approved"):
            await self._review_loop(ch, cs, paths, kind="slides")
            cs["slide_status"] = "rendered"
            log.info("%s 완료 (슬라이드 %d장)", ch["id"], cs.get("slide_count", 0))
            await self._save()
            await self._notify("장 완성", self._chapter_summary(ch))

    def _chapter_summary(self, ch: dict) -> str:
        cs = self.state.chapter(ch["id"])
        tr, sr = cs["text_reviews"], cs["slide_reviews"]
        flags = ["본문 기준 미달"] * bool(cs.get("text_forced")) + ["슬라이드 기준 미달"] * bool(cs.get("slides_forced"))
        done = sum(self._chapter_done(c["id"]) for c in self.state.data["plan"]["chapters"])
        return (f"{ch['id']} '{ch['title']}' 완성 — 본문 {tr[-1]['overall'] if tr else '-'}점, "
                f"슬라이드 {cs.get('slide_count', 0)}장 {sr[-1]['overall'] if sr else '-'}점"
                + (f" ({', '.join(flags)})" if flags else "")
                + f" · 진행 {done}/{len(self.state.data['plan']['chapters'])}장")

    async def _draft_text(self, ch: dict, paths: dict[str, Path]) -> None:
        log.info("%s 집필: %s", ch["id"], ch["title"])
        res = await ask(
            self.s, P.writer_prompt(self.state.data["plan"], ch, self.brief, self._chapter_no(ch["id"])),
            system=self.h.system("writer", P.writer_system(self.s)), schema=P.CHAPTER_SCHEMA,
            label=f"{ch['id']}-write",
        )
        paths["text"].write_text(_clean_md(res.data["markdown"]), encoding="utf-8")

    async def _draft_slides(self, ch: dict, paths: dict[str, Path]) -> None:
        log.info("%s 슬라이드 명세 작성", ch["id"])
        res = await ask(
            self.s, P.slides_prompt(ch, paths["text"].read_text(encoding="utf-8")),
            system=self.h.system("slides", P.slides_system(self.s)), schema=P.SLIDES_SCHEMA,
            label=f"{ch['id']}-slides",
        )
        self._write_spec(ch, paths, {"slides": res.data["slides"]})

    def _write_spec(self, ch: dict, paths: dict[str, Path], spec: dict) -> None:
        paths["spec"].write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
        paths["spec_md"].write_text(spec_to_markdown(spec, self._deck_title(ch)), encoding="utf-8")

    async def _build(self, ch: dict, paths: dict[str, Path], spec: dict) -> tuple[list[str], list[str]]:
        """덱을 빌드하고 (점검 오류, 미리보기 상대 경로)를 돌려준다."""
        try:
            result = await anyio.to_thread.run_sync(
                build_deck, spec, self._deck_title(ch), paths["pptx"], paths["preview"])
        except Exception as err:
            log.warning("%s 빌드 실패: %s", ch["id"], err)
            return [f"빌드 실패: {str(err)[:300]}"], []
        errors = result.layout_errors + [f"붙여넣기 호환: {e}" for e in result.paste_errors]
        previews = [str(p.relative_to(self.s.out_dir)).replace("\\", "/") for p in result.previews]
        return errors, previews

    def _lint(self, ch: dict, kind: str, current) -> list[str]:
        if kind == "text":
            return (lint_chapter(current, self.source_urls, self.s.min_chapter_chars)
                    + self.h.extra_lint("text", current))
        spec_text = "\n".join(v for s in current["slides"] for _, v in _text_fields(s))
        return lint_spec(current, ch["slide_count"]) + self.h.extra_lint("slides", spec_text)

    async def _review_loop(self, ch: dict, cs: dict, paths: dict[str, Path], kind: str) -> None:
        """결정적 점검 + LLM 검토 → 통과할 때까지(최대 max_revisions회) 수정. 끝나면 하네스 지표를 남긴다."""
        is_text = kind == "text"
        reviews: list = cs["text_reviews" if is_text else "slide_reviews"]
        base = cs.get(f"{kind}_review_base", 0)
        status_key = "text_status" if is_text else "slide_status"
        loop_start = len(reviews)
        version_at_start = self.h.version

        while True:
            attempt = len(reviews) - base
            if is_text:
                current = paths["text"].read_text(encoding="utf-8")
                lint = self._lint(ch, kind, current)
                prompt = P.review_prompt(ch, current, self.source_urls, lint)
                system, schema, tools = self.h.system("reviewer", P.reviewer_system(self.s)), P.REVIEW_SCHEMA, []
            else:
                current = json.loads(paths["spec"].read_text(encoding="utf-8"))
                build_errors, previews = await self._build(ch, paths, current)
                lint = self._lint(ch, kind, current) + build_errors
                prompt = P.slide_review_prompt(ch, paths["text"].read_text(encoding="utf-8"), current, lint, previews)
                system = self.h.system("slide_reviewer", P.slide_reviewer_system(self.s))
                schema, tools = P.SLIDE_REVIEW_SCHEMA, (["Read"] if previews else [])
                cs["slide_count"] = len(current["slides"])

            res = await ask(self.s, prompt, system=system, schema=schema, tools=tools,
                            max_turns=40 if tools else 8, label=f"{ch['id']}-{kind}-review{attempt}")
            review = res.data
            majors = [i for i in review["issues"] if i["severity"] == "major"]
            passed = review["overall"] >= self.s.pass_score and not majors and not lint
            reviews.append({
                "at": datetime.now().isoformat(timespec="seconds"), "harness_version": self.h.version,
                "overall": review["overall"], "scores": review["scores"],
                "lint": lint, "issues": review["issues"], "passed": passed,
            })
            decision = "통과" if passed else ("기준 미달로 종료" if attempt >= self.s.max_revisions else "수정")
            log.info("%s %s 검토 %d: %.1f점, major %d, lint %d → %s (하네스 v%d)", ch["id"], kind, attempt,
                     review["overall"], len(majors), len(lint), decision, self.h.version)

            if passed or attempt >= self.s.max_revisions:
                cs[status_key] = "approved"
                cs[f"{kind}_forced"] = not passed
                loop = reviews[loop_start:]
                self.h.record(topic=self.s.topic, chapter=ch["id"], kind=kind, version=version_at_start,
                              first_score=loop[0]["overall"], final_score=loop[-1]["overall"],
                              revisions=len(loop) - 1, first_lint=len(loop[0]["lint"]),
                              passed=passed, forced=not passed)
                await self._save()
                await self._after_loop()
                return

            if is_text:
                extra = "참고 자료 URL은 다음 목록에서만 고른다:\n" + "\n".join(f"- {u}" for u in self.source_urls)
                res = await ask(
                    self.s, P.revise_prompt("교재 원고", current, review["issues"], lint, extra),
                    system=self.h.system("writer", P.writer_system(self.s)), schema=P.CHAPTER_SCHEMA,
                    label=f"{ch['id']}-text-revise{attempt + 1}",
                )
                paths["text"].write_text(_clean_md(res.data["markdown"]), encoding="utf-8")
            else:
                res = await ask(
                    self.s, P.revise_slides_prompt(current, review["issues"], lint),
                    system=self.h.system("slides", P.slides_system(self.s)), schema=P.SLIDES_SCHEMA,
                    label=f"{ch['id']}-slides-revise{attempt + 1}",
                )
                self._write_spec(ch, paths, {"slides": res.data["slides"]})
            await self._save()

    async def _save(self) -> None:
        async with self.state.lock:
            self.state.save()

    # ============================================================ RSI: 자기 하네스 개선

    async def _after_loop(self) -> None:
        self._loops_since_improve += 1
        if self._loops_since_improve >= self.s.improve_every:
            await self.improve("검토 루프 체크포인트")

    async def improve(self, reason: str) -> dict | None:
        """L1: 실행 기록 → 하네스 개선안 → 정적 검증 → 시험 버전. 시험 중이면 먼저 판정한다.
        L2: 개선자 자신의 규칙(role=improver)도 같은 절차로 바뀐다."""
        if not self.s.self_improve or self._improve_lock.locked():
            return None
        async with self._improve_lock:
            self._loops_since_improve = 0
            verdict = self.h.evaluate_trial()
            if verdict:
                msg = (f"하네스 시험 판정: v{verdict['version']} → {verdict['verdict']} "
                       f"(품질 변화 {verdict['delta']:+.2f}, 표본 {verdict['samples']})")
                log.info(msg)
                self.state.event(msg)
                self.h.apply_config(self.s)
                await self._notify("하네스 판정", msg.replace("하네스 시험 판정: ", "")
                                   .replace("adopted", "채택").replace("rolled_back", "롤백"))
            if self.h.status == "trial":
                log.info("하네스 v%d 시험 중 — 표본이 더 쌓이면 판정", self.h.version)
                return None
            if self.h.samples_since_last_proposal() < self.s.improve_every:
                return None

            log.info("자기 개선 시작 (%s, 하네스 v%d)", reason, self.h.version)
            bounds = "\n".join(f"- {k}: {lo}~{hi} (현재 {getattr(self.s, k)})" for k, (lo, hi) in CONFIG_BOUNDS.items())
            res = await ask(
                self.s, P.improve_prompt(self.h.view(), self._telemetry(), self.h.track_record(), bounds),
                system=self.h.system("improver", P.improver_system()), schema=P.IMPROVE_SCHEMA, label="improve",
            )
            record = self.h.propose(res.data["diagnosis"], res.data["proposals"], self._corpus())
            self.h.apply_config(self.s)
            msg = (f"자기 개선: 제안 {len(res.data['proposals'])}개 중 {len(record['accepted'])}개 채택"
                   + (f" → 시험 버전 v{self.h.version}" if record["accepted"] else " → 변경 없음"))
            log.info(msg)
            for rej in record["rejected"]:
                log.info("  거부: %s", rej["reason"])
            if record["accepted"]:
                changes = "; ".join(_describe(p).split(" — 근거:")[0][:140] for p in record["accepted"])
                await self._notify("하네스 개선", f"시험 버전 v{self.h.version} 적용: {changes}")
            self.state.event(msg)
            await self._save()
            self.h.write_report()
            return record

    def _telemetry(self) -> str:
        rows = self.h.metrics()[-30:]
        lines = ["최근 검토 루프(버전, 종류, 장: 첫 점수 → 최종 점수, 수정 횟수, 첫 lint 수):"]
        lines += [f"- v{r['version']} {r['kind']} {r.get('topic', '')}/{r['chapter']}: {r['first_score']} → {r['final_score']}, "
                  f"수정 {r['revisions']}, lint {r['first_lint']}{', 기준 미달' if r['forced'] else ''}" for r in rows]
        lint_counter: Counter = Counter()
        issues: list[str] = []
        for cs in self.state.chapters.values():
            for kind, key in (("text", "text_reviews"), ("slides", "slide_reviews")):
                for rv in cs.get(key, [])[-4:]:
                    for e in rv["lint"]:
                        lint_counter[f"{kind}: " + re.sub(r"\d+", "N", e)[:120]] += 1
                    for i in rv["issues"]:
                        issues.append(f"{kind} [{i['severity']}] {i['problem'][:160]}")
        lines += ["", "자주 걸린 lint(정규화):"] + [f"- {n}회: {k}" for k, n in lint_counter.most_common(15)]
        lines += ["", "최근 검토 지적(최대 40개):"] + [f"- {x}" for x in issues[-40:]]
        return "\n".join(lines)

    def _corpus(self) -> dict[str, list[str]]:
        texts, slides = [], []
        for ch in self.state.data.get("plan", {}).get("chapters", []):
            paths = self._paths(ch)
            if paths["text"].exists():
                texts.append(paths["text"].read_text(encoding="utf-8"))
            if paths["spec"].exists():
                spec = json.loads(paths["spec"].read_text(encoding="utf-8"))
                slides.append("\n".join(v for s in spec["slides"] for _, v in _text_fields(s)))
        return {"text": texts, "slides": slides}

    # ============================================================ 데몬용: 가장 약한 결과물 다시 만들기

    async def refresh_cycle(self) -> dict:
        """완성된 교재에서 가장 점수가 낮은 장(본문 또는 슬라이드)을 현재 하네스로 다시 만든다.
        더 나아졌을 때만 교체하므로 결과물은 나빠지지 않는다. 새 지표는 하네스 시험 판정에 쓰인다."""
        candidates = []
        for ch in self.state.data["plan"]["chapters"]:
            cs = self.state.chapter(ch["id"])
            for kind, key in (("text", "text_reviews"), ("slides", "slide_reviews")):
                if cs.get(key):
                    refreshed = cs.get("refreshed", {}).get(kind, "")
                    candidates.append((cs[key][-1]["overall"], refreshed, ch, kind))
        if not candidates:
            return {"action": "없음", "result": "대상 없음"}
        candidates.sort(key=lambda c: (c[1] != "", c[0], c[1]))   # 아직 안 한 것 → 점수 낮은 것 → 오래된 것
        old_score, _, ch, kind = candidates[0]
        cs = self.state.chapter(ch["id"])
        paths = self._paths(ch)
        log.info("리프레시: %s %s (현재 %.1f점, 하네스 v%d)", ch["id"], kind, old_score, self.h.version)

        key = "text_reviews" if kind == "text" else "slide_reviews"
        backup_reviews = list(cs[key])
        files = [paths["text"]] if kind == "text" else [paths["spec"], paths["spec_md"]]
        backups = {p: p.read_bytes() for p in files if p.exists()}
        cs[f"{kind}_review_base"] = len(cs[key])

        if kind == "text":
            await self._draft_text(ch, paths)
            cs["text_status"] = "drafted"
        else:
            await self._draft_slides(ch, paths)
            cs["slide_status"] = "drafted"
        await self._review_loop(ch, cs, paths, kind)
        new_score = cs[key][-1]["overall"]
        cs.setdefault("refreshed", {})[kind] = datetime.now().isoformat(timespec="seconds")

        if new_score >= old_score:
            result = f"교체 {old_score:.1f} → {new_score:.1f}"
            if kind == "text":   # 본문이 바뀌었으니 슬라이드도 다시 만든다
                cs["slide_status"], cs["slides_review_base"] = "pending", len(cs["slide_reviews"])
                await self.produce_chapter(ch)
        else:
            for p, data in backups.items():
                p.write_bytes(data)
            cs[key] = backup_reviews + [dict(r, discarded=True) for r in cs[key][len(backup_reviews):]]
            cs[key].append(dict(backup_reviews[-1], at=datetime.now().isoformat(timespec="seconds"), restored=True))
            if kind == "slides":
                await self._build(ch, paths, json.loads(paths["spec"].read_text(encoding="utf-8")))
            result = f"유지(새 결과 {new_score:.1f} < 기존 {old_score:.1f})"
        cs["text_status"] = "approved"
        cs["slide_status"] = "rendered"
        self.state.event(f"리프레시 {ch['id']} {kind}: {result}")
        await self._save()
        self.publish()
        log.info("리프레시 결과: %s %s %s", ch["id"], kind, result)
        await self._notify("리프레시", f"{ch['id']} {'본문' if kind == 'text' else '슬라이드'} 다시 만들기: {result}")
        return {"action": f"리프레시 {ch['id']} {kind}", "result": result}

    # ============================================================ 4. 과정 전체 검토

    async def course_review(self, round_no: int, apply: bool) -> bool:
        """교재 전체를 검토한다. apply=True면 누락 주제는 새 장으로, 장 간 문제는 해당 장 수정으로 반영.
        반영할 변경이 있었으면 True."""
        plan = self.state.data["plan"]
        digests = []
        for ch in plan["chapters"]:
            path = self._paths(ch)["text"]
            if path.exists():
                digests.append(_digest(ch, path.read_text(encoding="utf-8")))
        log.info("과정 검토 %d (%s)", round_no + 1, "반영" if apply else "보고용")
        res = await ask(
            self.s, P.course_review_prompt(plan, digests, self.state.data["research"]["concepts"]),
            system=P.course_reviewer_system(self.s), schema=P.COURSE_REVIEW_SCHEMA, label=f"course-review{round_no}",
        )
        review = res.data
        review["round"], review["applied"] = round_no, apply
        self.state.data["course_reviews"].append(review)
        (self.s.reviews_dir / f"course_review_{round_no + 1}.json").write_text(
            json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("과정 검토: %.1f점, 누락 주제 %d, 장 이슈 %d",
                 review["overall"], len(review["missing_topics"]), len(review["chapter_issues"]))
        await self._notify("과정 검토", f"교재 전체 {review['overall']}점, 누락 주제 {len(review['missing_topics'])}개, "
                           f"장 간 이슈 {len(review['chapter_issues'])}개 — {review['summary'][:200]}")
        if not apply:
            await self._save()
            return False

        changed = False
        room = self.s.max_chapters - len(plan["chapters"])
        if review["missing_topics"] and room > 0:
            res = await ask(
                self.s, P.extend_prompt(plan, review["missing_topics"], len(plan["chapters"]) + 1, min(room, 2)),
                system=self.h.system("planner", P.planner_system(self.s)), schema=P.EXTEND_SCHEMA, label="plan-extend",
            )
            new_chapters = res.data["chapters"][: min(room, 2)]
            if new_chapters:
                plan["chapters"].extend(new_chapters)
                self._normalize_plan(plan)
                titles = [c["title"] for c in new_chapters]
                self.state.event(f"과정 검토 반영: 새 장 추가 {titles}")
                log.info("새 장 추가: %s", titles)
                (self.s.out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
                changed = True

        by_chapter: dict[str, list[dict]] = {}
        for issue in review["chapter_issues"]:
            by_chapter.setdefault(issue["chapter_id"], []).append(issue)
        known = {c["id"]: c for c in plan["chapters"]}
        for cid, issues in by_chapter.items():
            if cid not in known or not any(i["severity"] == "major" for i in issues):
                continue
            cs = self.state.chapter(cid)
            path = self._paths(known[cid])["text"]
            log.info("%s 과정 검토 의견 반영 수정", cid)
            res = await ask(
                self.s,
                P.revise_prompt("교재 원고", path.read_text(encoding="utf-8"),
                                [{"severity": i["severity"], "location": "교재 전체 관점", "problem": i["problem"], "fix": i["fix"]}
                                 for i in issues], []),
                system=self.h.system("writer", P.writer_system(self.s)), schema=P.CHAPTER_SCHEMA,
                label=f"{cid}-course-revise",
            )
            path.write_text(_clean_md(res.data["markdown"]), encoding="utf-8")
            cs["text_status"], cs["slide_status"] = "drafted", "pending"
            cs["text_review_base"], cs["slides_review_base"] = len(cs["text_reviews"]), len(cs["slide_reviews"])
            changed = True
        await self._save()
        return changed

    # ============================================================ 5. 발행

    def publish(self) -> None:
        plan = self.state.data["plan"]
        out = self.s.out_dir
        toc, combined, rows = [], [f"# {plan['title']}\n\n_{plan['subtitle']}_\n"], []
        for ch in plan["chapters"]:
            cs = self.state.chapter(ch["id"])
            paths = self._paths(ch)
            if not paths["text"].exists():
                continue
            no = self._chapter_no(ch["id"])
            combined.append(paths["text"].read_text(encoding="utf-8"))
            toc.append(f"{no}. [{ch['title']}]({paths['text'].name}) — {ch['summary']}")
            if paths["pptx"].exists():
                thumb = paths["preview"] / "slide-1.png"
                rows.append({
                    "title": f"{no}장. {ch['title']}", "count": cs.get("slide_count", 0),
                    "score": cs["slide_reviews"][-1]["overall"] if cs.get("slide_reviews") else "-",
                    "pptx": paths["pptx"].name, "pdf": paths["pdf"].name if paths["pdf"].exists() else "",
                    "spec": paths["spec_md"].name, "textbook": f"../textbook/{paths['text'].name}",
                    "thumb": str(thumb.relative_to(self.s.slides_dir)).replace("\\", "/") if thumb.exists() else "",
                })

        (self.s.textbook_dir / "README.md").write_text(_syllabus(plan, toc), encoding="utf-8")
        (self.s.textbook_dir / "full-textbook.md").write_text("\n\n---\n\n".join(combined), encoding="utf-8")
        (self.s.slides_dir / "index.html").write_text(render_index_html(plan["title"], plan["subtitle"], rows), encoding="utf-8")
        (self.s.reviews_dir / "final_report.md").write_text(self._final_report(), encoding="utf-8")
        (out / "README.md").write_text(
            f"# {plan['title']}\n\n{plan['subtitle']}\n\n"
            f"- 주제: {self.s.topic}\n- 대상: {plan['audience']}\n"
            f"- 교재: [textbook/README.md](textbook/README.md) · [전체 교재 한 파일](textbook/full-textbook.md)\n"
            f"- 슬라이드: [slides/index.html](slides/index.html) (장별 PPTX, PDF 미리보기, 슬라이드 명세 .md)\n"
            f"- 검토 보고서: [reviews/final_report.md](reviews/final_report.md)\n"
            f"- 리서치: [research/brief.md](research/brief.md)\n", encoding="utf-8")
        self.state.event("발행 완료")
        self.state.save()
        log.info("발행 완료: %s", out)

    def _final_report(self) -> str:
        plan = self.state.data["plan"]
        lines = [f"# 검토 보고서 — {plan['title']}", "",
                 f"생성 시각: {datetime.now():%Y-%m-%d %H:%M} · 하네스 v{self.h.version} ({self.h.status})", "",
                 "| 장 | 제목 | 본문 점수 | 본문 검토 횟수 | 슬라이드 점수 | 슬라이드 검토 횟수 | 상태 |",
                 "|---|---|---|---|---|---|---|"]
        for ch in plan["chapters"]:
            cs = self.state.chapter(ch["id"])
            tr = [r for r in cs["text_reviews"] if not r.get("discarded")]
            sr = [r for r in cs["slide_reviews"] if not r.get("discarded")]
            flags = []
            if cs.get("text_forced"):
                flags.append("본문 기준 미달")
            if cs.get("slides_forced"):
                flags.append("슬라이드 기준 미달")
            lines.append(
                f"| {ch['id']} | {ch['title']} | {tr[-1]['overall'] if tr else '-'} | {len(tr)} "
                f"| {sr[-1]['overall'] if sr else '-'} | {len(sr)} | {', '.join(flags) or '통과'} |")
        lines += ["", "## 남은 지적 사항(마지막 검토 기준)", ""]
        for ch in plan["chapters"]:
            cs = self.state.chapter(ch["id"])
            for kind, reviews in (("본문", cs["text_reviews"]), ("슬라이드", cs["slide_reviews"])):
                if reviews and not reviews[-1]["passed"]:
                    last = reviews[-1]
                    lines.append(f"- **{ch['id']} {kind}**: " + "; ".join(
                        [f"[{i['severity']}] {i['problem']}" for i in last["issues"]] + [f"[lint] {e}" for e in last["lint"]]))
        if self.state.data["course_reviews"]:
            cr = self.state.data["course_reviews"][-1]
            lines += ["", "## 과정 전체 검토", "", f"- 점수: {cr['overall']}", f"- 요약: {cr['summary']}"]
            lines += [f"- 누락 주제(참고): {t}" for t in cr["missing_topics"]]
            lines += [f"- {i['chapter_id']} [{i['severity']}] {i['problem']}" for i in cr["chapter_issues"]]
        lines += ["", "## 실행 정보", "", f"- 모델: {self.s.model}", f"- 이번 프로세스 LLM 호출: {ledger.calls}회",
                  f"- 이번 프로세스 보고 비용: ${ledger.cost_usd:.2f}",
                  "- 하네스 자기 개선 기록: [../../../harness/RSI_REPORT.md](../../../harness/RSI_REPORT.md)",
                  "", "## 진행 기록", ""]
        lines += [f"- {e['at']} {e['msg']}" for e in self.state.data["events"][-60:]]
        return "\n".join(lines) + "\n"


# ================================================================ helpers

def _clean_md(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:markdown|md)?\s*\n(.*)\n```$", text, re.S)
    return (m.group(1) if m else text).strip() + "\n"


def _check_urls(urls: list[str]) -> dict[str, bool]:
    """출처 URL이 실제로 존재하는지 확인한다. 봇 차단(401/403/429)은 존재하는 것으로 본다."""
    result = {}
    for url in urls:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 courseware-agent"})
        try:
            with urllib.request.urlopen(req, timeout=15):
                result[url] = True
        except urllib.error.HTTPError as err:
            result[url] = err.code in (401, 403, 405, 429, 999)
        except Exception:
            result[url] = False
    return result


def _brief_markdown(topic: str, data: dict) -> str:
    out = [f"# 리서치 브리프: {topic}", "", data["overview_md"], "", "## 핵심 개념", ""]
    out += [f"- **{c['term']}**: {c['definition']}" for c in data["key_concepts"]]
    out += ["", "## 실무 적용·모범 사례", ""] + [f"- {p}" for p in data["practices"]]
    out += ["", "## 사례", ""] + [f"- {c}" for c in data["case_studies"]]
    out += ["", "## 열린 질문", ""] + [f"- {q}" for q in data["open_questions"]]
    out += ["", "## 출처", ""]
    for src in data["sources"]:
        out.append(f"- [{src['title']}]({src['url']}) — {src['publisher']}, {src['date']}")
        out += [f"  - {k}" for k in src["key_points"]]
    return "\n".join(out) + "\n"


def _digest(ch: dict, text: str) -> str:
    heads = [ln for ln in text.splitlines() if ln.startswith("## ") or ln.startswith("### ")]
    summary = ""
    m = re.search(r"^## [^\n]*핵심 정리[^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    if m:
        summary = m.group(1).strip()[:1500]
    return f"### {ch['id']} {ch['title']}\n절 구성:\n" + "\n".join(heads) + f"\n핵심 정리:\n{summary}\n"


def _syllabus(plan: dict, toc: list[str]) -> str:
    out = [f"# {plan['title']}", "", f"_{plan['subtitle']}_", "", f"**대상**: {plan['audience']}", "",
           "## 선수 지식", ""] + [f"- {p}" for p in plan["prerequisites"]]
    out += ["", "## 과정 목표", ""] + [f"- {o}" for o in plan["course_outcomes"]]
    out += ["", "## 목차", ""] + toc
    out += ["", "## 장별 학습 목표", ""]
    for no, ch in enumerate(plan["chapters"], 1):
        out += [f"### {no}장. {ch['title']}", ""] + [f"- {o}" for o in ch["objectives"]] + [f"- 실습: {ch['hands_on']}", ""]
    return "\n".join(out) + "\n"
