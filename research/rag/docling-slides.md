# PPT 스크립트: Docling 소개와 PDF 로더 비교 (1장)

- 덱 파일: `research/rag/docling.pptx`  
- 빌드 코드: `research/rag/build/build-one-slide.js docling` (pptxgenjs). `references/pptx-guide.md`를 따름  
- 상세 문서: 별도 문서 없음. 「상세 보기」는 Docling 공식 문서로 연결  
- 총 1장. 16″ × 9″, `내용_단쪽` 레이아웃. 표지와 간지 없음  
- 글꼴은 모든 텍스트에 Pretendard를 직접 지정. 제목 32pt, 리드문 18pt, 본문과 표는 최소 14pt  
- 시각 배치: 2열 구성(슬라이드 유형 「소개_비교」). 좌측 4.3″(핵심 기능 번호 목록, RAG 연결 카드) /  
  우측 10.35″(세 도구 비교표, Docling 열 강조, 행 높이 자동). 아래에 콜아웃 한 줄,  
  오른쪽 아래 「상세 보기」 필 라벨(공식 문서 링크), 출처 한 줄  
- 아래의 「화면」 항목만 슬라이드에 표시함. 「발표자 노트」는 노트에 넣음

---

## 슬라이드 1. Docling

- 슬라이드 유형: 소개_비교
- 제목: Docling: 문서 구조를 읽어 RAG용으로 정제하는 변환 도구
- 리드문: AI 모델이 페이지의 문단, 표, 그림을 구분하고 읽는 순서대로 복원해 마크다운이나 JSON으로 내보냅니다.
- 좌상 배지: 핵심 기능
- 좌상 목록:
  1. 끊긴 줄을 문단과 제목으로 복원
  2. 병합 셀까지 표 구조 복원
  3. 스캔본은 OCR로 글자 추출
  4. 그림에 설명 문장 생성(옵션)
- 좌하 배지: RAG에 연결
- 좌하 카드:
  - LangChain: DoclingLoader로 바로 불러옴
  - HybridChunker: 문서 구조를 따라 청킹
  - 출력: 마크다운, HTML, JSON
- 우측 배지: PyMuPDF, pdfplumber와 비교
- 표 열 너비: [1.5, 2.95, 2.95, 2.95]

| 항목 | Docling | PyMuPDF | pdfplumber |
|---|---|---|---|
| 줄바꿈과 문단 | 문단, 제목, 읽는 순서 복원 | 레이아웃 AI로 제목과 문단 구분 | 줄 단위. 문단은 직접 조립 |
| 표 | 병합 셀까지 구조 복원 | find_tables와 레이아웃 AI | 선과 좌표 기준, 설정 세밀 |
| 스캔본(OCR) | 내장(EasyOCR 등) | RapidOCR 또는 Tesseract 설치 | 지원 안 함 |
| 그림 | VLM으로 설명 생성(옵션) | 이미지 추출 | 이미지 위치만 |
| 입력 형식 | PDF, DOCX, PPTX, HTML 등 | PDF, XPS, EPUB, 이미지 등 | PDF만 |
| 한글(HWP) | 지원 안 함 | 유료 Office 추가로 가능 | 지원 안 함 |
| 속도 | 느림(GPU 있으면 유리) | 매우 빠름 | PyMuPDF보다 느림 |
| 라이선스 | MIT(모델은 개별 라이선스) | AGPL 또는 상용 | MIT |

- 콜아웃: 표와 그림이 섞인 문서는 Docling, 대량 문서는 PyMuPDF, 정해진 위치의 값은 pdfplumber가 유리합니다.
- 상세 보기 링크: https://docling-project.github.io/docling/
- 화면 출처: Docling 공식 문서와 GitHub README. PyMuPDF GitHub README와 RAG 문서. pdfplumber GitHub README (2026-10-22 확인)
- 발표자 노트:
  - 핵심 한 줄: PDF는 글자를 "어느 좌표에 어떤 글자"로만 저장합니다. 그래서 단순 추출하면 문장이 줄마다 끊기고, 2단 문서는 왼쪽 단과 오른쪽 단이 섞이며, 표는 글자 나열로 무너집니다. Docling은 AI 모델로 페이지를 먼저 "이건 제목, 이건 문단, 이건 표"로 나눈 뒤 글을 꺼내므로 RAG에 넣기 좋은 깨끗한 글이 나옵니다.
  - 출신: IBM Research 취리히 팀이 시작한 오픈소스이고 지금은 LF AI & Data 재단 소속입니다. 코드는 MIT 라이선스이고, 내려받는 AI 모델은 모델마다 라이선스가 따로 있습니다.
  - 표: TableFormer 모델이 행과 열, 병합 셀을 복원합니다. 단, 병합 셀은 JSON과 HTML 출력에서는 유지되지만 마크다운은 병합 셀을 표현할 수 없어 풀립니다. 표가 중요한 문서는 JSON이나 HTML로 받는 편이 안전합니다.
  - 그림 설명: do_picture_description 옵션은 기본값이 꺼짐입니다. 켜면 SmolVLM이나 Granite Vision 같은 작은 VLM이 그림마다 설명 문장을 붙여, 그림 속 정보도 검색에 걸리게 됩니다.
  - OCR: 스캔본은 EasyOCR 같은 엔진을 골라 씁니다. 한국어 스캔본은 엔진마다 품질 차이가 커서 샘플 몇 장으로 먼저 확인해야 합니다.
  - PyMuPDF: C로 만든 MuPDF 엔진 위에 있어 매우 빠릅니다. 최신판에는 ONNX Runtime 기반 레이아웃 분석이 들어와 제목과 문단 구분, 읽는 순서, 표 인식이 좋아졌고, pymupdf4llm으로 마크다운을 바로 얻습니다. OCR은 RapidOCR(공식 권장)이나 Tesseract를 따로 설치해야 합니다. DOCX, PPTX, HWP 같은 Office 문서는 유료 라이선스 키가 필요한 PyMuPDF Office로 처리합니다. 라이선스가 AGPL이라 서비스에 넣어 배포하면 소스 공개 의무가 생기니, 그게 어려우면 상용 라이선스를 사야 합니다.
  - pdfplumber: pdfminer.six 위에 만든 순수 Python 도구로, 글자 하나하나의 좌표와 글꼴을 다룹니다. 표 추출 규칙을 세밀하게 조정하고 결과를 그림으로 겹쳐 보며 디버깅할 수 있어, 양식이 정해진 문서에서 특정 칸 값을 뽑을 때 강합니다. OCR은 없어서 스캔본은 다른 도구가 필요합니다.
  - 속도: 세 도구를 같은 조건으로 잰 공식 수치는 없어 상대 표현으로 적었습니다. Docling은 페이지마다 레이아웃 모델과 표 모델을 돌리므로 가장 느리고 GPU가 있으면 유리합니다.
  - HWP: 한국 공공 문서에서 자주 만나는 형식입니다. Docling과 pdfplumber는 지원하지 않으므로 PDF나 DOCX로 바꾼 뒤 넣습니다.
  - 실습 제안: 표가 있는 PDF 한 개를 세 도구로 각각 변환해 표 부분을 나란히 보면 차이가 바로 보입니다. 이어서 각 결과로 RAG 검색을 돌려 정답 청크가 걸리는지 비교하면, 정제 품질이 검색 품질로 이어진다는 점을 확인할 수 있습니다.
