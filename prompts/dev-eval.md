[목표]
{주제}: 품질 평가
{주제} 프로그램 개발

[역할]
클로니가 적절한 팀원과 수행
[맥락]
- 내 상황: 
  - 교육생들에게 {주제}에 대한 개발 샘플을 전달해야 함
- 독자: 교육생 
[입력]	
- {주제} 설계서: ~/Documents/강의/신한카드/{주제}설계서.pptx
- 레이어드아키텍처 가이드: references/layered-architecture-guide.md
- 주석 가이드: references/dev-comment-guide.md
- 인덱싱 프로그램: hybrid-ai-lab/indexer/vector-bm25
- 검색 프로그램: hybrid-ai-lab/retriever/vector-retriever

[처리]
- 입력 정보 파악 
- 개발 계획 수립 및 검토 
- 앱 개발 
	- CLI로 실행되도록 함 
- 테스트 및 버그 수정 
- README.md 작성 
	- 목표 및 주요 기능 
	- Workflow: Mermaid 스크립트로 작성 
	- 디렉토리 구조
	- 가상환경 설정 방법: OS(Window, Mac)와 Shell별(GitBash, Powershell)
	- 실행 방법 

[출력]
hybrid-ai-lab/ragas/(소스, requirements.txt, README.md)

[제약사항]
- MUST: 
	- 추가정보나 내 의사결정이 필요하면 반드시 요청 
	- Layered Architecture로 개발 
	- 주석가이드에 따라 주석 작성
	- LangChain 사용
	- use context7
- MUST NOT:
  - 추측하여 개발하지 말고 입력정보에 기반하여 개발  
- 완료조건
  - 테스트 통과 및 정상 수행 
