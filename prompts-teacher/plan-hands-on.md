[목표]
교육생들이 NL2SQL, RAG, RAGAS, GraphRAG, 온톨로지, MCP 등의   
기술 주제 개념을 파이썬 코드로 개발하면서 이해하도록 함.      
이를 위해 강사가 전체 예제 코드를 개발하고,   
교육생들은 핵심 프로그램을 클론 코딩하면서 이해도를 높이고자 함

이 목표 달성을 위한 계획을 세우는것이 목표임 

[역할]
클로니가 팀원들과 협의하여 최적안 제안 

[상황]
- 내 상황: 강사로서 예제 코드 제공 및 설명을 하고 교육생들이 직접 개발할 핵심 프로그램과 교체 방법을 전달해야 함
- 독자: 강사 

[입력]
- {example_dir}: ~/class/hybrid-ai/hybrid-ai-lab
- 교재: `~/Documents/강의/신한카드/신한카드 하이브리드AI_W01~W04.pptx` (3/4주차의 RAG만 참조)
- 주석가이드: references/dev-comment-guide.md
- RAG 인덱싱: {example_dir}/indexer/vector-bm25
- RAG 검색: {example_dir}/retriever/vector-retriever

[처리]
- 필수 요구사항
	- 교육생들이 개발할 핵심 프로그램 선별
	- 교육생들이 클론 코딩 후 본인 프로그램으로 교체 지원 
	- 기술주제에 대한 전체 예제 코드 개발
		- Layered Architecture 적용하지 않고 최대한 simple하게 개발: 
			- 프로그램 파일 수를 최소화하고 핵심 프로그램만 분리하여 import하는 구조 고려 
			- 환경설정 파일 등을 분리하지 말고 main 프로그램에 통합 
		- 예제는 파이썬 초보자들이 이해하기 쉽게 최대한 쉽게 개발 
			- 한 줄에 축약하는 수행이 좋더라도 여러줄로 풀어서 개발 
			- 하드코딩을 하더라도 여러 파일을 열어서 코드를 이해하지 않게 할 것 
		- 주석 가이드에 기반하여 최대한 쉽게 주석을 많이 달것 
	- 기술 주제 특성에 따라 교육생들이 핵심적인 단계의 주요 결과를 확인할 수 있도록 함 

- 예제 프로그램 개발 
	- RAG 인덱싱, 검색, RAGAS 예제 개발 
  	- 임베딩 모델은 KURE-v2 사용
  	- 리랭킹 모델은 Cohere rerank-v4.0-fast 사용 
	- {base_dir}: hands-on/solutions/rag
	- {base_dir}/{indexing|retriever|ragas}에 개발 
	- 가상환경 디렉토리는 '.venv'로 함 
	- LangChain 사용을 기본으로 하고 depreciated 된 경우 native 패키지 사용  
	- README.md 작성 
		- 목표 및 주요 기능 
		- 디렉토리 구조 
		- 가상환경 설정 및 패키지 설치: window(powershell, Git Bash), Mac/Linux별 
		- 실행 방법 
		
- 실습계획서 작성 
	- 교재에서 3~4주차의 RAG 파트 이해 
	- RAG 인덱싱, 검색, RAGAS 실습계획서 초안 작성
	- 팀원 리뷰
	- 실습계획서 최종안 작성 

[출력]
- 실습계획서: 'hands-on/plan/' 에 결과파일 작성 

[제약조건]
- MUST 
	- 추가정보나 내 의사결정이 필요하면 반드시 요청 
	- use context7
 