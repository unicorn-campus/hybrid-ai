# 리서치 브리프: 파이썬 AI 프로그램 하네스 엔지니어링

## 1. 정의: 하네스란 무엇인가

**하네스(harness)**는 LLM을 실제로 일하는 프로그램으로 만들기 위해 모델 바깥에 두는 코드, 설정, 실행 로직 전체를 말합니다. 여기에는 에이전트 루프, 도구 정의와 실행, 컨텍스트와 메모리 관리, 출력 검증, 권한과 가드레일, 재시도와 타임아웃, 상태 저장과 재개, 관측, 비용 한도, 평가가 들어갑니다. 널리 쓰이는 공식은 LangChain의 Vivek Trivedy가 정리한 **Agent = Model + Harness**입니다(2026-03-10). 같은 글에는 "모델이 아니면 전부 하네스"라는 표현도 나옵니다. **하네스 엔지니어링**은 이 바깥 구조를 의도적으로 설계하고, 테스트하고, 계속 고쳐 나가는 일입니다. 목표는 모델은 그대로 두고 신뢰성, 안전, 비용을 끌어올리는 것입니다.

### 출처마다 다른 정의 (교재에 명시할 것)
| 출처 | 정의의 초점 | 범위 |
|---|---|---|
| Mitchell Hashimoto (2026-02-05, "Engineer the Harness") | 에이전트가 실수할 때마다 같은 실수를 다시 못 하도록 해결책을 엔지니어링하는 **습관**. 수단은 AGENTS.md 갱신과 전용 스크립트/도구 | 실천 중심, 코딩 에이전트 사용자 관점 |
| LangChain / Trivedy (2026-03-10) | 모델을 뺀 **모든 것**: 파일시스템, bash·코드 실행, 샌드박스, 메모리, 컴팩션, 검증 루프 | 가장 넓은 정의 |
| Birgitta Böckeler, martinfowler.com (2026-04-02) | 위 넓은 정의를 인정한 뒤, 코딩 에이전트 **사용자가 자기 프로젝트에 덧씌우는 바깥 층**으로 좁힘. 가이드(feedforward)와 센서(feedback), 계산적 통제와 추론적 통제로 구분 | 사용자 측 바깥 하네스 |
| OpenAI Codex 팀 (2026-02, 원문은 403으로 직접 확인 못 함. InfoQ와 2차 요약으로 확인) | 엔지니어의 일이 코드 작성에서 **환경 설계, 의도 명세, 피드백 루프 구축**으로 옮겨감. 2차 요약에 따르면 "컨텍스트 엔지니어링은 에이전트가 무엇을 볼지, 하네스 엔지니어링은 시스템이 무엇을 막고, 측정하고, 교정할지"를 묻는다고 구분함 | 대규모 저장소 운영 |
| Anthropic evals 글 (2026-01-09) | 이 글은 **agent harness(=scaffold)**와 **evaluation harness**를 구분함. 앞의 것은 모델을 에이전트로 동작하게 하는 시스템이고, 뒤의 것은 평가를 처음부터 끝까지 돌리는 인프라 | 용어가 두 뜻으로 쓰임 |
| Meta-Harness 논문 (arXiv 2603.28052, 2026-03-30) | 모델이 무엇을 저장하고, 검색하고, **보게 될지를 통제하는 코드** | 컨텍스트 엔지니어링에 가까운 좁은 정의 |

교재에서는 **"하네스 = 모델 바깥의 런타임 구조(에이전트 하네스)"**를 기본 정의로 씁니다. 다만 소프트웨어 테스트에서 말하는 **test/eval harness**와 혼동하지 않도록 첫 장에서 두 뜻을 구분해 두는 것이 좋습니다. 이 과정은 두 가지를 모두 파이썬으로 구현합니다.

## 2. 등장 배경
1. **에이전트 패턴의 정착 (2024-12)**: Anthropic의 "Building effective agents"는 워크플로(미리 정한 코드 경로)와 에이전트(LLM이 스스로 도구 사용을 지휘)를 구분했습니다. 그리고 증강 LLM, 프롬프트 체이닝, 라우팅, 병렬화, 오케스트레이터-워커, 평가자-최적화자 패턴을 정리했습니다. 권고는 "가장 단순한 해법에서 시작하라"와 "프레임워크보다 API 직접 호출부터"였습니다.
2. **컨텍스트가 병목으로 드러남 (2025-09)**: "Effective context engineering"은 컨텍스트 부패(context rot)와 어텐션 예산 개념을 들어 컨텍스트를 유한한 자원으로 다뤄야 한다고 정리했습니다. 대응책으로 컴팩션, 구조화 노트, 서브에이전트, JIT 검색을 제시했습니다.
3. **장시간 에이전트 실험 (2025-11 ~ 2026-03)**: Anthropic은 initializer 에이전트와 coding 에이전트, feature list JSON, progress 파일, git 커밋으로 세션 사이의 기억 단절을 메웠습니다. 이어 planner, generator, evaluator 3-에이전트 구조로 몇 시간짜리 자율 개발을 시연했습니다.
4. **용어의 확산 (2026-02 ~ 04)**: Hashimoto 블로그(2/5), OpenAI Codex "harness engineering" 글(2/11, 2차 출처 기준), LangChain(3/10), Fowler 사이트 Böckeler 글(4/2)이 연달아 나오면서 "하네스 엔지니어링"이 독립된 분야 이름으로 자리 잡았습니다. 누가 처음 썼는지는 출처마다 다릅니다(Hashimoto설, LangChain 대중화설 등).
5. **자동 최적화 (2026-03)**: Meta-Harness는 코딩 에이전트가 이전 후보들의 코드, 점수, 실행 트레이스를 읽고 하네스 코드를 직접 고치는 바깥 루프를 제안했습니다. 하네스를 사람이 설계하는 대상에서 탐색하는 대상으로 넓힌 셈입니다.

## 3. 왜 지금 중요한가
- **모델이 같아도 하네스가 성능을 좌우합니다.** Anthropic 멀티에이전트 리서치 시스템은 단일 에이전트 대비 내부 평가에서 90.2% 더 높은 성능을 냈습니다. Meta-Harness는 같은 모델에서 하네스만 바꿔 분류 과제 +7.7점, 수학 RAG +4.7점을 보고했습니다.
- **비용이 크게 늘어납니다.** 에이전트는 채팅의 약 4배, 멀티에이전트는 약 15배의 토큰을 씁니다. 하네스를 추가하면 레트로 게임 메이커 사례에서 $9/20분이 $200/6시간으로 늘었습니다. 그래서 예산 한도, 프롬프트 캐싱, effort 조절이 하네스의 기본 기능이 되었습니다.
- **비결정성 때문에 테스트 방식이 바뀌어야 합니다.** pass@k와 pass^k를 구분하고, 회귀 eval을 CI에 넣지 않으면 개선과 퇴행을 구분할 수 없습니다.
- **SDK가 하네스 부품을 직접 제공합니다.** Anthropic Python SDK는 재시도 기본 2회, 타임아웃 기본 10분, `_request_id`, OpenTelemetry 스팬, `messages.parse`, `tool_runner`를 제공합니다. Claude Agent SDK는 `max_turns`, `max_budget_usd`, hooks, `can_use_tool`, `resume`/`fork_session`, `output_format`, `total_cost_usd`를 제공합니다. 파이썬 개발자가 이 부품들을 직접 조립하고 시험할 수 있게 되었습니다.
- **모델이 좋아지면 하네스도 바뀌어야 합니다.** Anthropic은 "하네스의 모든 구성요소는 모델이 혼자 못 하는 것에 대한 가정"이라고 했습니다. 실제로 Opus 4.6에서는 스프린트 구조를 걷어냈습니다. 하네스는 한 번 만들고 끝나는 물건이 아니라 eval로 계속 검증하며 고치고 줄여야 하는 코드입니다.

## 4. 과정 범위와의 연결
이 과정은 위 내용을 **파이썬 실습** 순서로 다룹니다. 에이전트 루프(Messages API 직접 구현 후 tool_runner와 Agent SDK와 비교), 도구(ACI 설계, `@beta_tool`, `@tool` + `create_sdk_mcp_server`, strict tool use), 컨텍스트와 메모리(컴팩션, 도구 출력 오프로딩, progress 파일), 구조화 출력(`messages.parse` + pydantic, Pydantic AI `output_validator`/`ModelRetry`), 가드레일과 권한(`PreToolUse` 훅, `permission_mode`, `disallowed_tools`), 재시도와 타임아웃(SDK 기본값 + 애플리케이션 수준 백오프와 멱등성), 상태 저장과 재개(session_id, resume/fork, 체크포인트), eval과 회귀(pytest로 task·trial·grader 구조와 pass^k 구현), 관측(logging, request_id, OTel GenAI 스팬), 비용(usage 집계, 캐싱, 예산 한도), 자기 개선 루프(실패 트레이스에서 하네스 수정 후 eval로 게이트) 순입니다. Claude Code와 Codex의 AGENTS.md/CLAUDE.md 작성법은 "사용자 측 바깥 하네스"의 예로만 짧게 비교합니다.

## 핵심 개념

- **하네스 (Agent Harness)**: 모델을 뺀 모든 코드, 설정, 실행 로직입니다. 루프, 도구, 컨텍스트, 상태, 가드레일, 관측을 포함합니다. Agent = Model + Harness(LangChain). Anthropic은 scaffold와 같은 뜻으로 씁니다. 출처에 따라 '사용자가 덧씌우는 바깥 층'(Böckeler)이나 '모델이 보고, 저장하고, 검색하는 것을 통제하는 코드'(Meta-Harness)로 좁혀 쓰기도 합니다.
- **평가 하네스 (Evaluation Harness)**: eval을 처음부터 끝까지 실행하고, 각 단계를 기록하고, 채점하고, 결과를 집계하는 인프라입니다. 에이전트 하네스와 다른 개념이며, eval 점수는 항상 '모델 + 에이전트 하네스' 조합을 측정한다는 점에 유의해야 합니다(Anthropic, 2026-01).
- **하네스 엔지니어링**: 하네스를 설계, 구현, 측정, 개선하는 분야입니다. Hashimoto는 에이전트가 실수할 때마다 재발을 막는 장치를 만드는 습관으로, OpenAI는 환경 설계·의도 명세·피드백 루프 구축으로, Böckeler는 가이드와 센서를 조합해 결과에 대한 신뢰를 쌓는 일로 설명합니다.
- **에이전트 루프 (Agentic Loop)**: 프롬프트를 받으면 모델이 응답하거나 tool_use를 요청하고, 하네스가 도구를 실행해 tool_result를 돌려주는 과정을 반복하다가 도구 호출 없는 응답이 나오면 끝납니다. 한 번 도는 것을 turn이라 하며, max_turns와 max_budget_usd 같은 정지 조건이 필수입니다.
- **워크플로 vs 에이전트**: 워크플로는 LLM과 도구를 미리 정한 코드 경로로 엮는 방식이고, 에이전트는 LLM이 스스로 절차와 도구 사용을 결정하는 방식입니다. 단순한 쪽에서 시작해 필요할 때만 복잡도를 올리라는 것이 Anthropic의 권고입니다.
- **ACI (Agent-Computer Interface)**: 에이전트가 쓰는 도구의 인터페이스입니다. HCI만큼 공을 들여야 하며, 신입 개발자용 문서처럼 설명을 쓰고, 오용을 막는 poka-yoke 설계(예: 절대경로 강제), 네임스페이싱, 토큰 효율적인 응답(페이지네이션, response_format), 실행 가능한 에러 메시지를 갖춰야 합니다.
- **컨텍스트 엔지니어링**: 추론 시점에 모델이 보는 토큰 전체(시스템 프롬프트, 도구, 예시, 히스토리, 검색 결과)를 골라 관리하는 일입니다. 프롬프트 엔지니어링을 포함하는 상위 개념이며, 하네스 엔지니어링의 하위 영역으로 보는 견해(Fowler, LangChain)와 별도 분야로 보는 견해(OpenAI 2차 요약)가 함께 있습니다.
- **컨텍스트 부패 / 어텐션 예산**: 컨텍스트가 길어질수록 정보를 정확히 떠올리는 능력이 떨어지는 현상입니다. 그래서 컨텍스트를 수확 체감이 있는 유한 예산으로 보고, 원하는 결과를 내는 가장 작은 고신호 토큰 집합을 찾아야 합니다.
- **컴팩션 / 컨텍스트 리셋**: 컴팩션은 한도에 가까워진 대화를 요약해 다시 시작하는 방식이고, 컨텍스트 리셋은 구조화된 인계 산출물(progress 파일, feature list, git log)을 남기고 새 컨텍스트로 갈아타는 방식입니다. Anthropic은 일부 모델의 'context anxiety' 때문에 컴팩션만으로는 부족해 리셋이 필요했다고 보고했습니다.
- **도구 출력 오프로딩 / JIT 검색**: 큰 도구 출력은 앞부분과 끝부분만 컨텍스트에 남기고 전체는 파일로 저장하는 방식입니다. 데이터는 미리 다 싣지 않고 경로·쿼리·링크 같은 가벼운 참조만 들고 있다가 필요할 때 불러옵니다.
- **구조화 출력 (Structured Outputs)**: JSON 스키마로 응답을 제약하는 기능입니다. Anthropic은 JSON outputs(output_config.format, Python에서는 messages.parse와 pydantic)와 strict tool use(strict: true)를 제공합니다. 스키마 유효성은 보장되지만, refusal이나 max_tokens로 응답이 잘린 경우는 따로 처리해야 하고, minimum/maxLength 같은 제약은 로컬에서 검증해야 합니다.
- **출력 검증기와 ModelRetry**: Pydantic AI의 @agent.output_validator 안에서 ModelRetry를 던지면 오류 이유를 모델에 돌려주고 다시 생성하게 합니다. 재시도 예산은 기본 1회이며 Agent(retries={'output': N})로 바꿀 수 있습니다.
- **가이드와 센서 (Feedforward / Feedback)**: 가이드는 행동 전에 방향을 잡아 주는 장치(규약 문서, AGENTS.md, 코드모드)이고, 센서는 행동 후 관찰해 스스로 고치게 하는 장치(린터, 구조 테스트, AI 리뷰)입니다. 한쪽만 있으면 실수를 되풀이하거나 규칙이 효과가 있었는지 알 수 없습니다(Böckeler).
- **계산적 통제 vs 추론적 통제**: 계산적 통제는 테스트, 타입 검사, 린터처럼 결정적이고 빠르고 싸며 매 변경마다 돌릴 수 있습니다. 추론적 통제는 LLM-as-judge처럼 느리고 비결정적이지만 의미를 판단할 수 있습니다. 가능하면 계산적 통제를 먼저 씁니다.
- **훅 (Hooks)**: Claude Agent SDK에서 PreToolUse, PostToolUse, Stop, PreCompact 같은 이벤트에 등록하는 콜백입니다. deny/allow/ask/defer 결정, updatedInput으로 입력 수정, additionalContext 주입, 감사 로깅을 할 수 있습니다. 여러 훅의 결정이 엇갈리면 deny가 가장 우선합니다.
- **권한 모드 (Permission Mode)**: Agent SDK의 default, acceptEdits, plan, dontAsk, auto, bypassPermissions입니다. allowed_tools는 '자동 승인'일 뿐 다른 도구를 막지는 않습니다. 차단은 disallowed_tools와 규칙(예: Bash(rm *))으로 하고, 판단이 필요한 호출은 can_use_tool 콜백으로 넘어갑니다.
- **세션, resume, fork**: 세션은 프롬프트, 도구 호출, 결과의 누적 기록이며 JSONL로 디스크에 저장됩니다. resume은 session_id로 이어서 진행하고, fork_session은 기록을 복제해 다른 방향으로 갈라집니다. 둘 다 대화만 저장하며 파일시스템 변경은 file checkpointing으로 따로 다룹니다.
- **Task / Trial / Grader / Transcript / Outcome**: agent eval의 기본 단위입니다. 각각 성공 기준이 있는 테스트 하나, 한 번의 시도, 채점 로직, 전체 기록(trace), 환경의 최종 상태를 뜻합니다. 경로보다 결과(outcome)를 채점하는 편이 권장됩니다.
- **pass@k vs pass^k**: pass@k는 k번 중 한 번 이상 성공할 확률이고, pass^k는 k번 모두 성공할 확률입니다. 시도당 성공률이 75%이면 pass^3은 약 42%입니다. 고객 대면 에이전트처럼 일관성이 중요하면 pass^k를 봅니다.
- **Capability eval vs Regression eval**: capability eval은 낮은 통과율에서 출발해 개선 여지를 측정하고, regression eval은 거의 100%를 유지해야 하는 회귀 방지 스위트입니다. 포화된 capability 과제는 regression 스위트로 옮깁니다.
- **Generator-Evaluator (GAN 영감)**: 생성 에이전트와 회의적으로 튜닝한 별도 평가 에이전트를 분리하는 구조입니다. 자기 평가 편향을 줄이며, 스프린트 계약(완료 기준 사전 합의)과 하드 임계값을 함께 씁니다.
- **Ralph 루프**: 에이전트가 일찍 끝내려 할 때 훅이 이를 막고 새 컨텍스트에서 다시 프롬프트하는 루프입니다. 반복 사이의 상태는 파일시스템이 이어 줍니다(LangChain).
- **프롬프트 캐싱**: tools, system, messages 순서의 동일한 접두부를 캐시하는 기능입니다. 5분 쓰기는 1.25배, 1시간 쓰기는 2배, 읽기는 약 0.1배 가격입니다(모델별 예외 있음). 도구 정의나 앞부분 메시지가 바뀌면 캐시가 무효화되고, usage의 cache_creation/cache_read 필드로 효과를 확인합니다.
- **하네스 자동 최적화 (Meta-Harness)**: 코딩 에이전트인 proposer가 이전 후보들의 소스, 점수, 실행 트레이스를 파일시스템으로 읽고 새 하네스 코드를 제안하는 바깥 루프입니다. 자기 개선 루프를 하네스 수준으로 넓힌 사례입니다.

## 실무 적용·모범 사례

- [출발점] 프레임워크보다 Anthropic Messages API로 에이전트 루프를 직접 50줄 안팎으로 구현해 봅니다. while 루프로 stop_reason == 'tool_use'이면 도구를 실행해 tool_result를 붙이고, 'end_turn'이면 종료합니다. 그다음 client.beta.messages.tool_runner와 Claude Agent SDK query()로 같은 과제를 다시 구현하며 하네스가 대신해 주는 부분을 비교합니다(Building effective agents의 '단순하게 시작' 원칙).
- [루프 정지 조건] 모든 루프에 max_turns, 누적 비용 상한, 벽시계 시간 상한을 동시에 둡니다. Agent SDK에서는 ClaudeAgentOptions(max_turns=30, max_budget_usd=...)를 쓰되, 한도를 넘긴 응답 하나만큼 초과할 수 있으므로 여유를 둡니다. ResultMessage.subtype이 error_max_turns 또는 error_max_budget_usd인 경우를 분기 처리하고 session_id를 저장해 resume 경로를 만들어 둡니다.
- [도구 설계] 도구는 적게, 워크플로 단위로 만듭니다(list_all 대신 search). 이름은 서비스_리소스_동작으로 네임스페이싱하고, 파라미터는 user_id처럼 모호하지 않게 정합니다. 응답에는 response_format('concise'|'detailed'), 페이지네이션, 잘라내기 기본값을 넣고, 에러 메시지는 다음 행동을 알려 주게 씁니다. 상대경로를 거부하는 식으로 poka-yoke 검증을 도구 함수 안에 둡니다.
- [도구 정의 코드] Anthropic SDK에서는 @beta_tool로 타입 힌트와 docstring에서 스키마를 만들고, 입력은 pydantic 모델로 한 번 더 검증합니다. 스키마 준수가 중요하면 strict: true와 additionalProperties: false를 씁니다. Agent SDK에서는 @tool과 create_sdk_mcp_server로 인프로세스 MCP 서버를 만들고, 읽기 전용 도구에는 readOnlyHint를 주어 병렬 실행을 허용합니다.
- [도구 실행 격리] 도구 실행을 하네스 쪽 executor 함수 하나로 모읍니다. 여기서 도구별 타임아웃(asyncio.wait_for), 예외를 is_error tool_result로 변환하는 처리, 출력 크기 상한(앞뒤만 남기고 전체는 파일로 오프로딩), 감사 로그를 공통으로 처리합니다. 예외를 루프 밖으로 던지지 말고, 모델이 읽고 고칠 수 있는 메시지로 돌려줍니다.
- [컨텍스트 관리] 컨텍스트 예산을 측정합니다(count_tokens, usage). 큰 검색 결과는 경로·ID 같은 참조만 남기고 필요할 때 불러옵니다(JIT). 오래된 tool_result는 지우거나 요약하고, 한도에 가까우면 컴팩션하거나 구조화 인계 파일(progress.md, features.json)을 남긴 뒤 새 컨텍스트로 리셋합니다. Agent SDK에서는 PreCompact 훅으로 원본 트랜스크립트를 보관하고 compact_boundary 이벤트를 로깅합니다.
- [장기 메모리] Anthropic 장시간 하네스 패턴을 파이썬으로 재현합니다. initializer 단계에서 features.json(모두 passes:false), progress 파일, init 스크립트, 첫 git 커밋을 만들고, 매 세션은 '상태 읽기, 기능 하나 선택, 기본 E2E 테스트, 구현, 검증, 커밋, progress 갱신' 루틴을 지킵니다. 에이전트가 고칠 수 있는 필드를 passes로 제한하는 검증을 코드로 강제합니다.
- [구조화 출력] 추출과 분류 단계는 client.messages.parse(output_format=PydanticModel)로 받습니다. 스키마가 지원하지 않는 제약(min/max, 길이, 교차 필드 규칙)은 pydantic field_validator나 model_validator로 로컬에서 검증합니다. stop_reason이 'refusal'이거나 'max_tokens'이면 별도로 분기하고, enum은 대소문자를 무시하고 비교합니다.
- [검증 후 재시도] 의미 검증(예: 인용한 문서 ID가 실제 검색 결과에 있는지)에 실패하면 오류 내용을 모델에 돌려주고 재생성하되, 재시도 횟수를 제한합니다. Pydantic AI에서는 @agent.output_validator와 ModelRetry, Agent(retries={'output': 2})로 구현하고, Agent SDK에서는 output_format을 쓰면서 error_max_structured_output_retries를 처리합니다.
- [가드레일과 권한] 최소 권한 원칙을 적용합니다. Agent SDK에서 allowed_tools는 '자동 승인'일 뿐이므로 차단은 disallowed_tools와 규칙('Bash(rm *)')으로 하고, 무인 실행은 permission_mode='dontAsk'로, bypassPermissions는 격리된 컨테이너에서만 씁니다. PreToolUse 훅으로 비밀 파일과 시스템 경로 쓰기를 deny하고, 매처가 도구 이름만 본다는 점(Bash 우회)을 샌드박스로 보완합니다.
- [사람 승인] 돌이킬 수 없는 동작(결제, 메일 발송, DB 쓰기)은 can_use_tool 콜백이나 PreToolUse의 'ask'/'defer'로 사람 승인 게이트를 둡니다. defer로 멈춘 호출은 나중에 재개합니다. 승인 요청과 결정은 모두 감사 로그에 남깁니다.
- [입력 측 가드레일] RAG와 웹 도구가 가져온 외부 텍스트는 신뢰하지 않는 데이터로 취급합니다. 시스템 지시와 구분되는 태그로 감싸고, 도구 결과로 권한이 오르지 않도록 고위험 도구는 별도 승인 경로로만 열어 둡니다(프롬프트 인젝션 대비).
- [재시도와 타임아웃] SDK 기본값(재시도 2회, 타임아웃 10분)을 그대로 쓰지 말고 용도에 맞게 명시합니다. 예: Anthropic(max_retries=3, timeout=httpx2.Timeout(60, connect=5)). 긴 생성은 스트리밍으로 받고, RateLimitError와 APIConnectionError는 애플리케이션 수준에서 지수 백오프와 지터, 서킷 브레이커로 감쌉니다. 부작용이 있는 도구는 멱등 키를 써서 재시도 중 중복 실행을 막습니다.
- [상태 저장과 재개] 루프의 각 턴이 끝날 때마다 메시지 히스토리, 도구 실행 기록, 비용 누계를 체크포인트(JSONL/SQLite)로 저장해 프로세스가 죽어도 마지막 턴부터 재개할 수 있게 합니다. Agent SDK에서는 ResultMessage.session_id로 resume하고, 다른 접근을 시험할 때는 fork_session=True를 씁니다. 파일 변경은 세션과 별개이므로 git이나 file checkpointing으로 되돌립니다.
- [eval 설계] 실제 실패와 수동 점검에서 20~50개 과제로 시작합니다. 과제마다 입력, 참조 해답, 결과(outcome) 채점 기준을 두고, 행동이 일어나야 하는 경우와 일어나면 안 되는 경우를 균형 있게 넣습니다. 채점은 결정적 코드 grader를 먼저 쓰고, LLM-as-judge는 루브릭과 사람 라벨로 보정한 뒤에만 씁니다.
- [pytest 회귀 스위트] @pytest.mark.parametrize로 과제를 돌리고, 과제마다 k번 시도해 pass^k를 assert합니다. CI에서는 실제 API를 부르는 eval과, 녹화된 응답이나 가짜 모델(Pydantic AI TestModel 등)로 루프·도구·검증 로직만 보는 단위 테스트를 분리합니다. 점수, 비용, 지연 시간을 기준선과 비교해 퇴행하면 실패시킵니다.
- [트랜스크립트 읽기] eval 점수만 보지 말고 실패한 트랜스크립트를 직접 읽어 grader가 공정한지, 과제가 모호하지 않은지 확인합니다. 통과율이 포화된 capability 과제는 regression 스위트로 옮기고 새 과제를 추가합니다.
- [관측] 모든 LLM 호출에 run_id, turn, request._request_id, 모델, usage(input/output/cache), 지연 시간, stop_reason을 구조화 JSON 로그로 남깁니다. OpenTelemetry로 '에이전트 실행 > 모델 호출 / 도구 실행' 스팬 계층을 만들고, 프롬프트와 출력 원문 수집은 개인정보 정책에 따라 opt-in으로 둡니다. GenAI 시맨틱 규약은 아직 개발 단계이므로 버전을 고정합니다.
- [비용 관리] usage에서 매 호출 비용을 계산해 run 단위로 누적하고, Agent SDK는 total_cost_usd와 서브에이전트를 포함하는 model_usage로 회계합니다. 정적 부분(tools, system, 긴 문서)은 앞에 두고 cache_control로 캐싱하되 타임스탬프 같은 가변값은 브레이크포인트 뒤로 보냅니다. 단순 단계는 작은 모델이나 낮은 effort로 라우팅하고, 대량 오프라인 작업은 Message Batches로 처리합니다.
- [자기 개선 루프] '실패 수집, 원인 분류, 하네스 수정(프롬프트, 도구 설명, 검증기, 가이드 문서), 회귀 eval 게이트, 배포' 주기를 자동화합니다. 에이전트가 하네스 코드나 프롬프트를 고치게 하더라도 held-out eval을 통과해야만 병합되게 하고, 변경 이력과 점수를 파일로 남겨 다음 제안자가 읽게 합니다(Meta-Harness 방식). 사람 리뷰 단계를 남겨 보상 해킹을 막습니다.
- [하네스 다이어트] 모델을 업그레이드할 때마다 하네스 구성요소를 하나씩 끄는 ablation eval을 돌려, 더 이상 성능을 떠받치지 않는 부분은 제거합니다(Anthropic이 Opus 4.6에서 스프린트를 제거한 사례).
- [코딩 에이전트와 비교, 배경 수준] Claude Code나 Codex의 AGENTS.md/CLAUDE.md는 '가이드(feedforward)' 하네스의 예로만 다룹니다. 실수가 반복될 때마다 한 줄씩 추가하는 Hashimoto 방식, 문서를 지도로 쓰고 린터와 구조 테스트로 강제하는 OpenAI 방식을 짧게 보여 주고, 같은 원리를 파이썬 애플리케이션의 시스템 프롬프트, 도구 설명, 검증기 설계로 옮겨 적용합니다.

## 사례

- Anthropic 장시간 코딩 하네스(2025-11): claude.ai 클론을 목표로 initializer 에이전트가 200개 이상의 기능을 JSON feature list(모두 failing)로 만들고, coding 에이전트가 세션마다 기능 하나씩 구현, 브라우저 E2E 검증, git 커밋, progress 갱신을 반복했습니다. 조기 완료 선언과 문서화되지 않은 중간 상태 문제를 구조화된 산출물로 해결했습니다.
- Anthropic 3-에이전트 하네스(2026-03): 레트로 게임 메이커를 단독 에이전트로 만들면 20분/$9였지만 핵심 기능이 고장 났고, planner-generator-evaluator 하네스로는 6시간/$200에 훨씬 완성도 높은 결과가 나왔습니다. Opus 4.6에서는 스프린트 구조를 없애고 평가를 마지막 한 번으로 줄인 단순화 하네스로 DAW를 약 3시간 50분/$124.70에 만들었습니다. 하네스는 모델 능력에 맞춰 줄여야 한다는 교훈입니다.
- Anthropic 멀티에이전트 리서치(2025-06): 오케스트레이터-워커 구조로 단일 에이전트 대비 내부 eval에서 90.2% 높은 성능을 냈지만, 토큰은 채팅의 약 15배를 썼습니다. 약 20개 쿼리의 소규모 eval, 루브릭 기반 LLM-as-judge, 사람 평가를 함께 썼고, 운영에서는 체크포인트 재개, 전체 트레이싱, rainbow 배포를 적용했습니다. 비용, eval, 관측, 재개를 한 사례에서 모두 보여 줍니다.
- OpenAI Codex 내부 실험(2025-08 ~ 2026-01, InfoQ와 2차 출처 기준): 빈 저장소에서 시작해 사람이 코드를 직접 쓰지 않고 약 5개월 만에 약 100만 줄 규모의 베타 제품을 만들었습니다. 구조화된 docs 디렉터리를 단일 진실 원천으로 삼고, 커스텀 린터와 구조 테스트로 계층 의존 방향을 기계적으로 강제했으며, 에이전트가 로그·메트릭·스팬을 읽어 버그를 재현하게 했습니다. 원문은 접근이 막혀 직접 확인하지 못했습니다.
- Ghostty 프로젝트(Mitchell Hashimoto, 2026-02): 에이전트가 잘못된 명령을 쓰거나 잘못된 API를 찾는 일이 반복될 때마다 AGENTS.md에 한 줄씩 추가하고, 스크린샷이나 필터링 테스트 같은 전용 스크립트를 만들어 알렸습니다. 각 줄이 과거의 실패 하나에 대응하는 실패 주도 하네스의 예입니다.
- Meta-Harness(Stanford·MIT·KRAFTON, 2026-03): 코딩 에이전트가 이전 하네스 후보의 코드, 점수, 트레이스를 읽고 새 하네스를 제안하는 자동 탐색으로 텍스트 분류 +7.7점(컨텍스트 토큰 4배 절감), 수학 RAG에서 보지 않은 모델 5종 평균 +4.7점, TerminalBench-2에서 수작업 하네스를 넘는 결과를 보고했습니다. 자기 개선 루프 단원의 연구 사례로 씁니다.
- LangChain 코딩 에이전트(2026, 2차 요약 기준): 모델을 바꾸지 않고 하네스 기법(검증 루프, 컨텍스트 관리 등)만으로 Terminal Bench 2.0 점수를 52.8%에서 66.5%로 올려 순위가 Top 30에서 Top 5로 올랐다고 알려져 있습니다. 수치는 원문에서 직접 확인하지 못했으므로 교재에 인용할 때 재확인이 필요합니다.

## 열린 질문

- 용어의 경계: 하네스를 '모델 외 전부'(LangChain), '사용자가 덧씌우는 바깥 층'(Böckeler), '모델이 보는 정보를 통제하는 코드'(Meta-Harness) 중 무엇으로 정의할지 합의가 없습니다. 컨텍스트 엔지니어링을 하네스의 하위 영역으로 볼지 별도 분야로 볼지도 갈립니다. 용어를 처음 쓴 사람(Hashimoto설 vs LangChain·OpenAI 대중화설)도 출처마다 다릅니다.
- 단일 범용 에이전트와 전문화된 멀티에이전트(테스터, QA, 클린업) 중 무엇이 나은가: Anthropic도 미해결로 남겼고, 멀티에이전트는 성능을 올리는 대신 토큰을 약 15배 씁니다.
- 모델이 좋아질수록 어떤 하네스 구성요소가 쓸모없어지는가: 구성요소를 언제, 어떤 eval로 걷어낼지에 대한 체계적인 방법론이 아직 없습니다. 하네스 설계 공간이 줄어드는지 단지 이동하는지도 논쟁 중입니다.
- 행동(behaviour) 검증의 신뢰성: AI가 생성한 테스트와 LLM-as-judge를 얼마나 믿을 수 있는지, 보정에 필요한 사람 라벨 규모가 어느 정도인지 정해져 있지 않습니다(Böckeler는 아직 충분하지 않다고 봄).
- 비결정성 아래의 CI 설계: pass^k를 쓰려면 k배의 비용이 들고, 녹화 응답과 가짜 모델로는 실제 모델 회귀를 잡지 못합니다. 비용과 신뢰도 사이의 표준 절충안이 없습니다.
- 컴팩션과 컨텍스트 리셋 중 무엇을 기본값으로 할지: 모델마다 'context anxiety' 정도가 달라 최적 전략이 모델 의존적이고, 요약 과정에서 초기 지시가 사라지는 문제의 일반 해법이 없습니다.
- 자기 개선 루프의 안전성: 에이전트가 하네스나 프롬프트, 검증기를 스스로 고칠 때 eval 과적합, 보상 해킹, 가드레일 약화를 어떻게 막을지(held-out 세트, 사람 리뷰 지점, 변경 범위 제한) 정해진 표준이 없습니다.
- 프레임워크 vs 직접 구현: API 직접 호출을 권하는 입장(Anthropic)과 Agent SDK, Pydantic AI, LangGraph 같은 하네스 프레임워크를 쓰는 입장 사이에서, 교육과 운영에 적합한 추상화 수준이 무엇인지 열려 있습니다. SDK의 빠른 변경(httpx2 전환, API 버전 2026-10-21, output_format에서 output_config.format으로 이전)도 유지보수 비용을 늘립니다.
- 관측 표준의 성숙도: OpenTelemetry GenAI 규약은 별도 저장소로 옮겨졌고 정식 버전이 없습니다. 에이전트, 도구, 서브에이전트 스팬과 프롬프트 원문 수집(개인정보) 방식이 앞으로 바뀔 수 있습니다.
- 권한과 가드레일의 완전성: 도구 이름 기반 훅 매처는 Bash 우회를 막지 못하고, auto 모드 분류기와 프롬프트 인젝션 방어도 확률적입니다. 결정적 샌드박스와 확률적 분류기를 어떻게 조합해야 충분히 안전한지 기준이 없습니다.
- 비용 대비 가치 판단: 하네스가 비용을 20배 이상 늘리는 사례가 있어, 어떤 과제에 무거운 하네스(evaluator, 멀티에이전트)를 쓸지 정하는 정량 기준(과제 난이도, 실패 비용)이 정립되지 않았습니다.

## 출처

- [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) — Anthropic Engineering, 2024-12-19
  - 워크플로(미리 정한 경로)와 에이전트(LLM이 도구 사용을 스스로 지휘)를 구분하고, 기본 블록으로 '증강 LLM(검색·도구·메모리)'을 제시함
  - 프롬프트 체이닝, 라우팅, 병렬화(sectioning/voting), 오케스트레이터-워커, 평가자-최적화자 패턴을 정리함
  - 에이전트에는 정지 조건(최대 반복 등), 샌드박스 테스트, 가드레일이 필요하고 사람 체크포인트를 둘 수 있음
  - ACI에 HCI만큼 투자할 것을 권함: 도구 설명은 신입 개발자용 문서처럼 쓰고, poka-yoke(절대경로 강제 등)로 오용을 막음
  - 프레임워크는 추상화로 프롬프트와 응답을 가리므로 API 직접 호출부터 시작하라고 권함
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — Anthropic Engineering, 2025-09-29
  - 컨텍스트 엔지니어링을 추론 시점의 토큰 전체를 골라 관리하는 일로 정의하고, 프롬프트 엔지니어링의 상위 개념으로 봄
  - 컨텍스트 부패와 어텐션 예산 개념을 들어, 원하는 결과를 내는 최소한의 고신호 토큰을 쓰라고 함
  - 시스템 프롬프트는 '적절한 고도'에서 써야 함: 하드코딩된 if-else와 막연한 지침을 모두 피함
  - 도구는 자기완결적이고 토큰 효율적이며 서로 겹치지 않게 만들고, 예시는 소수의 정형 few-shot으로 충분함
  - JIT 검색, 컴팩션(오래된 도구 결과 지우기 포함), 구조화 노트, 서브에이전트로 장기 과제를 다룸
- [Writing effective tools for agents — with agents](https://www.anthropic.com/engineering/writing-tools-for-agents) — Anthropic Engineering, 2025-09-11
  - 모든 API 엔드포인트를 감싸지 말고 영향이 큰 워크플로에 맞춘 소수의 도구를 만들 것
  - 서비스와 리소스별 접두어로 네임스페이싱하되, 최적 방식은 모델마다 다르므로 테스트할 것
  - 저수준 ID 대신 사람이 읽을 수 있는 고신호 필드를 반환하고, response_format(concise/detailed)으로 상세도를 고르게 함
  - 페이지네이션, 필터, 잘라내기 기본값과 실행 가능한 에러 메시지로 토큰을 아낌
  - 현실적인 다단계 eval 과제로 에이전트를 돌리고, 트랜스크립트와 지표를 분석해 도구를 개선하며, held-out 세트로 일반화를 확인함
- [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) — Anthropic Engineering, 2025-06-13
  - 오케스트레이터-워커 구조: 리드 에이전트(Opus 4)가 병렬 서브에이전트(Sonnet 4)를 띄우고 CitationAgent가 출처를 붙임
  - 내부 리서치 eval에서 단일 에이전트보다 90.2% 높은 성능을 냄. BrowseComp에서는 토큰 사용량이 성능 분산의 약 80%를 설명함
  - 토큰 사용량은 에이전트가 채팅의 약 4배, 멀티에이전트가 약 15배
  - eval은 약 20개 쿼리의 소규모 표본, 루브릭 기반 LLM-as-judge(0.0~1.0), 사람 평가를 병행함
  - 운영 측면: 상태 오류가 누적되므로 체크포인트에서 재개하고, 전체 트레이싱과 rainbow 배포를 씀
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — Anthropic Engineering (Justin Young), 2025-11-26
  - 세션마다 기억이 끊기는 문제는 컴팩션만으로 해결되지 않음. 실패 패턴은 한 번에 너무 많이 하기와 너무 이른 완료 선언
  - initializer 에이전트가 init.sh, progress 파일, 첫 git 커밋을 만들고, coding 에이전트는 한 번에 기능 하나씩 진행함
  - feature list는 JSON으로 관리함(claude.ai 클론에서 200개 이상, 모두 failing으로 시작). 에이전트는 passes 필드만 바꿀 수 있음. 마크다운보다 JSON이 덜 함부로 덮어써짐
  - 세션 시작 루틴: 작업 디렉터리 확인, git log와 progress 읽기, 최우선 미완 기능 선택, init.sh와 E2E 기본 테스트 실행
  - 브라우저 자동화(Puppeteer MCP)로 사람처럼 테스트하게 하자 성능이 크게 오름. 단일 범용 에이전트와 전문 멀티에이전트 중 무엇이 나은지는 미해결로 남김
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — Anthropic Engineering (M. Grace, J. Hadfield, R. Olivares, J. De Jonghe), 2026-01-09
  - task, trial, grader, transcript, outcome를 정의하고 evaluation harness와 agent harness를 구분함
  - grader는 코드 기반(빠르고 재현 가능하지만 깨지기 쉬움), 모델 기반(유연하지만 비결정적이라 보정 필요), 사람(최고 품질이지만 비쌈)으로 나뉨
  - capability eval은 낮은 통과율에서 출발하고, regression eval은 약 100%를 유지함. 포화된 과제는 regression으로 옮김
  - pass@k는 한 번 이상 성공, pass^k는 모두 성공. 75%면 pass^3 ≈ 42%
  - 로드맵: 실제 실패에서 20~50개 과제로 시작, 모호하지 않은 과제와 참조 해답, 격리된 환경, 경로보다 결과 채점, 트랜스크립트 읽기, 포화 감시
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps) — Anthropic Engineering (Prithvi Rajasekaran, Labs), 2026-03-24
  - context anxiety(한도가 가까워졌다고 여겨 일찍 마무리하는 현상)와 자기 평가 편향을 핵심 문제로 꼽음. 컴팩션보다 구조화된 인계를 동반한 컨텍스트 리셋이 효과적이었음
  - GAN에서 착안한 generator-evaluator 분리. 회의적인 별도 평가자를 튜닝하는 편이 generator의 자기비판보다 다루기 쉬움
  - planner, generator, evaluator 3-에이전트 구조. 평가자는 Playwright로 실제 앱을 조작하고 하드 임계값으로 스프린트를 판정하며, 스프린트 계약으로 완료 기준을 미리 합의함
  - 비용 비교: 단독 실행 20분/$9(핵심 기능 고장) vs 전체 하네스 6시간/$200. Opus 4.6에서는 스프린트를 없애고 DAW 빌드 약 3시간 50분/$124.70
  - 하네스의 각 구성요소는 모델 한계에 대한 가정이므로 모델이 바뀌면 다시 검증하고, 더 이상 하중을 받지 않는 부분은 제거하라고 함
- [My AI Adoption Journey (Step 5: Engineer the Harness)](https://mitchellh.com/writing/my-ai-adoption-journey) — Mitchell Hashimoto (개인 블로그), 2026-02-05
  - harness engineering을 에이전트가 실수할 때마다 재발하지 않도록 해결책을 엔지니어링하는 일로 정의함
  - 목표는 에이전트가 자신이 틀렸음을 빠르게 알거나 맞았음을 확인할 수 있는 고품질 수단을 주는 것
  - 수단 1: AGENTS.md 같은 암묵적 프롬프트 갱신. Ghostty의 AGENTS.md는 각 줄이 과거의 잘못된 행동에서 나왔다고 함
  - 수단 2: 스크린샷, 필터링된 테스트 실행 같은 전용 스크립트와 도구. 보통 AGENTS.md 갱신과 함께 씀
- [Harness engineering for coding agent users](https://martinfowler.com/articles/harness-engineering.html) — martinfowler.com (Birgitta Böckeler, Thoughtworks), 2026-04-02
  - '모델 외 전부'라는 넓은 정의를 인정한 뒤, 코딩 에이전트 사용자가 자기 프로젝트에 만드는 바깥 하네스로 범위를 좁힘
  - 가이드(feedforward)와 센서(feedback)를 둘 다 써야 함. 센서 메시지는 LLM이 읽기 좋게 쓰면 더 효과적임
  - 계산적 통제(테스트, 린터, 타입)와 추론적 통제(LLM-as-judge)를 구분함
  - 규제 차원은 유지보수성(가장 쉬움), 아키텍처 적합성(fitness function), 행동(가장 어려움. AI가 생성한 테스트는 아직 충분히 신뢰하기 어려움)
  - harnessability(타입 언어, 명확한 모듈 경계일수록 하네스를 걸기 쉬움)와 하네스 템플릿(Ashby의 법칙)을 제시함. 사람의 역할은 반복되는 문제가 생길 때 가이드와 센서를 개선하는 것
- [The Anatomy of an Agent Harness](https://www.langchain.com/blog/the-anatomy-of-an-agent-harness) — LangChain Blog (Vivek Trivedy), 2026-03-10
  - Agent = Model + Harness. 하네스는 모델에 없는 상태, 도구 실행, 피드백 루프, 제약을 제공함
  - 구성요소: 파일시스템(세션 간 내구 상태, git), bash와 코드 실행, 샌드박스(허용 목록, 네트워크 격리)
  - 메모리와 검색(AGENTS.md 주입, 웹 검색), 컨텍스트 관리(컴팩션, 도구 출력 오프로딩, skills의 점진적 공개)
  - 검증 루프: 훅으로 테스트를 돌리거나 자기 평가를 시켜 오류를 모델에 되먹임
  - Ralph 루프: 조기 종료를 막고 새 컨텍스트로 다시 프롬프트하며, 상태는 파일시스템으로 이어감
- [OpenAI Introduces Harness Engineering: Codex Agents Power Large-Scale Software Development](https://www.infoq.com/news/2026/02/openai-harness-engineering-codex) — InfoQ, 2026-02-21
  - OpenAI 원문(openai.com/index/harness-engineering, Ryan Lopopolo, 2026-02-11)은 403으로 직접 확인하지 못해 이 2차 보도로 대신함
  - 소수 엔지니어가 프롬프트와 피드백만 주고, 5개월 동안 수동 작성 코드 없이 약 100만 줄 규모의 베타 제품을 만듦
  - 구조화된 docs 디렉터리(지도, 실행 계획, 설계 명세)를 에이전트의 단일 진실 원천으로 삼고 린터와 CI로 검증함
  - 구조 테스트로 계층 의존 방향(types부터 UI까지)과 아키텍처 경계를 기계적으로 강제함
  - 에이전트가 로그, 메트릭, 스팬을 써서 격리 환경에서 버그를 재현함. 독립 검증이나 결함 지표는 기사에 없음
- [Claude Agent SDK reference — Python](https://code.claude.com/docs/en/agent-sdk/python) — Anthropic (Claude Code Docs), 2026-11 확인 (상시 갱신 문서)
  - query()는 호출마다 새 세션을 열고, ClaudeSDKClient는 세션을 유지하며 interrupt()를 지원함
  - ClaudeAgentOptions: allowed_tools(자동 승인일 뿐 제한 아님), disallowed_tools(예: 'Bash(rm *)'), permission_mode, can_use_tool, hooks, max_turns, max_budget_usd, resume/fork_session, output_format(json_schema), mcp_servers, setting_sources
  - @tool 데코레이터와 create_sdk_mcp_server로 인프로세스 도구를 정의함. 이름 규칙은 mcp__<server>__<tool>이고 ToolAnnotations(readOnlyHint)는 보안 장치가 아니라 힌트임
  - ResultMessage: subtype(success, error_max_turns, error_max_budget_usd, error_max_structured_output_retries 등), structured_output, total_cost_usd, usage(메인 루프만), model_usage(서브에이전트 포함), session_id
  - max_budget_usd는 클라이언트 측 추정치 기준이라 여유를 두어야 함
- [How the agent loop works (Agent SDK)](https://code.claude.com/docs/en/agent-sdk/agent-loop) — Anthropic (Claude Code Docs), 2026-11 확인 (상시 갱신 문서)
  - 루프: 프롬프트 수신, 평가와 응답, 도구 실행, 반복, ResultMessage. 메시지 타입은 SystemMessage, AssistantMessage, UserMessage, StreamEvent, ResultMessage
  - max_turns와 max_budget_usd의 기본값은 무제한이며 운영 환경에서는 예산 설정을 권장함. 한도를 넘긴 응답 하나만큼 초과할 수 있음
  - 읽기 전용 도구는 병렬, 상태를 바꾸는 도구는 순차로 실행됨. 커스텀 도구는 readOnlyHint가 있어야 병렬로 돎
  - 컨텍스트가 한도에 가까우면 자동 컴팩션되고 compact_boundary가 발생함. 영구 규칙은 CLAUDE.md에 두고 PreCompact 훅으로 원본을 보관함
  - 단발 query()는 에러 결과를 낸 뒤 예외를 던지므로 try로 감싸야 함. stop_reason으로 refusal과 max_tokens를 판별함
- [Intercept and control agent behavior with hooks](https://code.claude.com/docs/en/agent-sdk/hooks) — Anthropic (Claude Code Docs), 2026-11 확인 (상시 갱신 문서)
  - Python 지원 이벤트: PreToolUse, PostToolUse, PostToolUseFailure, UserPromptSubmit, Stop, SubagentStart/Stop, PreCompact, PermissionRequest, Notification 등. SessionStart/End는 Python 콜백으로는 쓸 수 없음
  - PreToolUse의 permissionDecision은 allow, deny, ask, defer이고 updatedInput으로 입력을 바꿀 수 있음. PostToolUse는 additionalContext와 updatedToolOutput을 쓸 수 있음
  - 여러 훅의 결정은 deny > defer > ask > allow 순으로 우선함. 훅은 병렬로 실행되므로 서로 독립적으로 작성해야 함
  - matcher는 도구 이름만 비교함. Write|Edit 훅은 Bash로 우회한 쓰기를 막지 못하므로 샌드박스가 필요함
  - 기본 타임아웃은 대부분 600초. PreToolUse 훅이 시간을 넘기면 도구 호출이 차단됨. 로깅처럼 부수효과만 있는 훅은 async_ 출력을 씀
- [Work with sessions (Agent SDK)](https://code.claude.com/docs/en/agent-sdk/sessions) — Anthropic (Claude Code Docs), 2026-11 확인 (상시 갱신 문서)
  - 세션은 대화(프롬프트, 도구 호출, 결과)만 저장하며, 파일 변경 되돌리기는 file checkpointing으로 따로 함
  - continue_conversation은 가장 최근 세션, resume은 특정 ID, fork_session은 복제 분기
  - error_max_turns나 error_max_budget_usd로 끝난 세션도 session_id가 있으므로 한도를 높여 resume할 수 있음
  - 세션은 ~/.claude/projects/<encoded-cwd>/*.jsonl에 저장됨. 다른 호스트에서 재개하려면 SessionStore 어댑터를 쓰거나 파일을 옮김
  - 대안: 세션 재개에 의존하지 않고 결과와 결정을 애플리케이션 상태로 저장해 새 세션에 주입하는 편이 더 견고할 때가 많음
- [Python SDK (Anthropic Client SDK)](https://platform.claude.com/docs/en/api/sdks/python) — Anthropic (Claude Platform Docs), 2026-11 확인 (상시 갱신 문서)
  - 재시도: 연결 오류, 408, 409, 429, 5xx를 기본 2회 지수 백오프로 재시도함. max_retries를 클라이언트나 요청별(with_options)로 조절함
  - 타임아웃: 기본 10분, float 또는 httpx2.Timeout으로 세분화함. 초과하면 APITimeoutError가 나고 이것도 재시도 대상. 긴 요청은 스트리밍을 권장함
  - 에러 계층: APIConnectionError, RateLimitError(429), APIStatusError 하위 클래스. 모든 응답의 _request_id를 로깅에 씀
  - @beta_tool과 client.beta.messages.tool_runner로 도구 루프를 자동화하고, count_tokens와 usage로 토큰을 측정함
  - ANTHROPIC_LOG=debug 로깅, OpenTelemetry 트레이서가 있으면 요청마다 스팬을 냄. SDK 2.x는 httpx2를 쓰고 API 버전 2026-10-21로 이전됨(버전 민감)
- [Structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) — Anthropic (Claude Platform Docs), 2026-11 확인 (상시 갱신 문서)
  - JSON outputs(output_config.format)와 strict tool use(strict: true)를 함께 쓸 수 있으며, 스키마에 맞는 유효한 JSON을 보장함
  - Python에서는 client.messages.parse()에 pydantic 모델을 넘기고 parsed_output으로 받음
  - 미지원 기능: 재귀 스키마, minimum/maximum, minLength/maxLength 등. SDK 헬퍼가 이런 제약을 설명문으로 옮기고 로컬에서 검증함
  - stop_reason이 refusal이거나 max_tokens이면 스키마 불일치나 잘림이 생길 수 있어 별도 처리가 필요함
  - 처음 쓰는 스키마는 컴파일 지연이 있고 24시간 캐시됨. 구 output_format 파라미터는 output_config.format으로 대체됨
- [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — Anthropic (Claude Platform Docs), 2026-11 확인 (상시 갱신 문서)
  - 최상위 cache_control을 쓰는 자동 캐싱과, 블록별 브레이크포인트를 최대 4개까지 두는 명시적 캐싱이 있음
  - 접두부 순서는 tools, system, messages이며 100% 동일해야 캐시가 맞음. 도구 정의가 바뀌면 전체가 무효화됨
  - TTL은 5분(쓰기 1.25배) 또는 1시간(쓰기 2배). 읽기는 기본 0.1배이며 일부 모델은 더 낮음
  - usage의 cache_creation_input_tokens와 cache_read_input_tokens로 효과를 측정함. 둘 다 0이면 최소 길이 미달일 가능성이 큼
  - 타임스탬프 같은 요청별 값이 브레이크포인트 앞에 있으면 캐시가 절대 맞지 않음
- [Pydantic AI — Output](https://pydantic.dev/docs/ai/core-concepts/output/) — Pydantic, 2026-11 확인 (상시 갱신 문서)
  - output_type으로 pydantic 모델, TypedDict, union 등을 지정하고, 허용된 타입이 반환되면 실행이 끝남
  - 출력 모드: Tool Output(기본), NativeOutput(공급자의 구조화 출력), PromptedOutput(프롬프트에 스키마 주입, 신뢰도 가장 낮음)
  - @agent.output_validator에서 ModelRetry를 던지면 재생성함. 출력 재시도 예산은 기본 1이고 Agent(retries={'output': N}) 등으로 조절함
  - 스트리밍(stream_output)으로 부분 결과를 받고 validation_context로 검증 맥락을 줄 수 있음
- [Meta-Harness: End-to-End Optimization of Model Harnesses](https://arxiv.org/abs/2603.28052) — arXiv (Y. Lee, R. Nair, Q. Zhang, K. Lee, O. Khattab, C. Finn), 2026-03-30
  - 하네스를 모델이 무엇을 저장하고, 검색하고, 보게 될지를 통제하는 코드로 정의하고, 대부분 아직 사람이 손으로 설계한다고 지적함
  - 코딩 에이전트인 proposer가 이전 모든 후보의 소스, 점수, 실행 트레이스를 파일시스템으로 읽고 하네스 코드를 탐색함
  - 기존 텍스트 최적화기는 피드백을 너무 압축한다고 보고, 풍부한 이력 접근을 핵심으로 삼음
  - 온라인 텍스트 분류에서 +7.7점(컨텍스트 토큰 4배 절감), IMO급 수학 RAG에서 보지 않은 모델 5종 평균 +4.7점, TerminalBench-2에서 수작업 최고 기준선을 넘음
- [OpenTelemetry Semantic Conventions for Generative AI (repository)](https://github.com/open-telemetry/semantic-conventions-genai) — OpenTelemetry, 2026-11 확인
  - 기존 opentelemetry.io의 GenAI 에이전트 스팬 페이지는 더 이상 유지되지 않으며 규약이 이 별도 저장소로 옮겨졌음(직접 확인)
  - GenAI 클라이언트, MCP, 공급자별 규약의 스팬, 메트릭, 이벤트를 다루며 Python 참조 구현의 준수 매트릭스가 있음
  - 확인 시점에 정식 릴리스 버전이 없고 Schema URL이 TODO 상태라 아직 성숙하지 않은 규약임
  - invoke_agent, execute_tool 같은 operation 이름과 gen_ai.* 속성은 검색 결과로만 확인했으므로, 실습 전에 docs/와 model/ 원문으로 재확인해야 함
