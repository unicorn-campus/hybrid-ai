# 공통 정형 DB (PostgreSQL)

하이브리드 AI 실습 **전 교육 과정**이 함께 쓰는 정형 데이터베이스임.
교육용 합성 데이터 전용이며 실제 고객·상품·금액이 아님.

## 상담이력이 있는 실습 회원 12명

`docs/D3_S*.txt` 6개 파일의 회원ID를 추출하여 실행 중인 `cardlab` DB와 대조한 결과임.
세그먼트별 2명, 회원별 상담 4건임. 점검일: 2026-09-09.

| 세그먼트 | 회원ID (`member_id`) | 보유카드 수 | 전체 거래 건수 | 승인 거래 건수 |
|---|---|---:|---:|---:|
| 1 신규 가입 | `M-1001` | 1 | 64 | 58 |
| 1 신규 가입 | `M-1050` | 1 | 115 | 109 |
| 2 장기 보유 | `M-1042` | 2 | 260 | 247 |
| 2 장기 보유 | `M-2048` | 2 | 277 | 264 |
| 3 VIP | `M-3001` | 2 | 181 | 168 |
| 3 VIP | `M-3049` | 2 | 181 | 168 |
| 4 휴면 직전 | `M-4001` | 1 | 304 | 291 |
| 4 휴면 직전 | `M-4049` | 1 | 253 | 240 |
| 5 다중 카드 | `M-5001` | 4 | 281 | 268 |
| 5 다중 카드 | `M-5049` | 4 | 266 | 253 |
| 6 연회비 부담 | `M-6001` | 2 | 297 | 284 |
| 6 연회비 부담 | `M-6049` | 2 | 307 | 294 |
| 합계 | 12명 | 24 | 2,786 | 2,644 |

- 12명 모두 `member`에 존재하며 카드와 거래 레코드가 연결됨. 카드 24장은 모두 `ACTIVE`임.
- 전체 거래는 `card_txn`의 승인·취소 레코드 합계임. 승인 거래는 `approval_code='APPROVED'` 기준임.
- 12명 모두 가입일 이후 대상 월의 승인 이용금액이 100만원 이상임. 취소 거래는 월 사용액에서 제외함.
- `M-1001`의 미이용 및 `M-4001`·`M-4049`의 최근 승인 0건 사례는 추가 거래 반영 후 더 이상 해당하지 않음.
- 2026-09-09 사용자 요청에 따라 승인 거래 1,152건을 추가함. 기존 거래·회원·카드는 유지함.

상담과 정형 데이터를 함께 조회할 때 사용할 회원ID 목록임.

```sql
WHERE member_id IN (
    'M-1001', 'M-1050', 'M-1042', 'M-2048',
    'M-3001', 'M-3049', 'M-4001', 'M-4049',
    'M-5001', 'M-5049', 'M-6001', 'M-6049'
)
```

거래는 `card_txn.card_id = card.card_id`로 연결한 뒤 `card.member_id`로 필터링함.
상담 원문·정제 방법은 [D3 사용 안내](../docs/D3_README.md)를 참조함.

## 상담 고객 월 100만원 이상 추가 거래

2025년 8월~2026년 8월 중 가입일 이후 142개 고객·월에 적용함.
월 사용액은 승인 거래 합계이며 혜택 실적·청구금액과는 다른 값임.
기존 거래는 유지하고 `D3ADD-` 접두어 거래 1,152건만 추가함.
재실행 시 같은 ID의 거래는 중복 삽입하지 않으며, 같은 ID의 내용이 다르면 적용을 중단함.

상담의 소비 감소·앱 불편·생활비 절약을 참고한 교육용 합성 설계임.
업종 분류만으로 온라인 결제·가전 품목·마트/외식을 구분하거나 해지·인증 성공을 확정하지 않음.
기존 미이용·휴면 반례는 나머지 회원에서 찾을 수 있으며, 이번 12명은 월 사용액 하한 적용 대상임.

```bash
python rdb/add_consultation_transactions.py          # 확정 추가 거래 JSON으로 SQL 생성
python rdb/add_consultation_transactions.py --apply  # 실행 중인 DB에 중복 없이 적용
python rdb/check_consultation_transactions.py        # 검증·상담 집계·README 갱신
```

`data/consultation_transactions.json`은 확정 추가 거래와 월별 전후 금액임.
`init/03_consultation_transactions.sql`은 신규 DB 생성 시 `02_seed.sql` 다음에 자동 실행됨.
따라서 전체 DB를 재생성해도 추가 거래가 유지됨. 기존 볼륨에는 `--apply`로 반영함.
검증 결과는 `data/consultation_transactions_audit.json`에 저장함.

## 기동과 종료

```bash
docker compose -f rdb/compose.yml up -d      # 기동(최초 1회에 스키마·데이터 자동 적재)
docker compose -f rdb/compose.yml ps         # 상태 확인
docker compose -f rdb/compose.yml down       # 중지(데이터 유지)
docker compose -f rdb/compose.yml down -v    # 중지 + 데이터 삭제(다음 기동 때 재적재)
```

초기화 스크립트는 **볼륨이 비어 있을 때만** 실행됨. 스키마나 데이터를 바꾼 뒤 다시 넣으려면
`down -v`로 볼륨을 지우고 다시 기동해야 함.

## 접속 정보

| 항목 | 값 |
|------|-----|
| 호스트·포트 | `localhost:5432` |
| 데이터베이스 | `cardlab` |
| 관리 계정 | `cardlab` / `cardlab` — 전체 권한. 원본 전체를 읽는 오프라인 도구도 이 계정을 씀 |
| 검색기 계정 | `sql_retriever_user` / `cardlab` — `app` 논리 뷰만 읽음, 원본 테이블 권한 없음 |
| 뷰 소유자 | `app_reader` — 로그인 불가. `app` 뷰를 소유하며 RLS 정책이 이 역할에 걸림 |
| 컨테이너 | `hybrid-ai-lab-rdb` (postgres:18-alpine) |
| 볼륨 | `hybrid-ai-lab-pgdata` |

```bash
docker exec -it hybrid-ai-lab-rdb psql -U cardlab -d cardlab
```

서비스 코드(검색기 등)는 **`sql_retriever_user`만** 씀. 원본 테이블과 재식별 열쇠에 손이 닿지 않는 것을  
계정 수준에서 보장하기 위함임.  
스키마 추출, 그래프 모델 검증처럼 원본 테이블 구조나 전체 행을 읽어야 하는 오프라인 도구는  
관리 계정 `cardlab`을 씀. 이 계정은 쓰기 권한과 `private` 접근 권한도 있으므로  
강사 PC 안에서만 쓰고 수강생에게 나눠 주지 않음.

### 행 수준 보안(RLS)과 논리 뷰

`member` · `card` · `card_txn` · `delinquency` 네 테이블에 행 수준 보안을 켜 둠.
정형 검색기(`retriever/sql-retriever`)가 자연어 질문으로 SQL을 만들 때 다른 회원의 행에
닿지 못하게 하려는 것임. 기본 뷰와 정책은 `init/04_views_rls.sql`, 가맹점·업종 집계 뷰는
`init/05_merchant_usage.sql`에 있음.

월별 연체 이력과 일별 승인 집계는 `init/06_history_daily_usage.sql`에 있음.  
신규 DB는 초기화 때 자동 적용하며, 기존 DB에는 05 다음에 06을 적용함.

가맹점·업종 집계는 `app.merchant_usage`에서 카드·월·가맹점별 승인 금액과 건수를 제공함.
최초·최근 승인일도 함께 제공하지만 개별 거래 행과 원본 카드·가맹점 ID는 노출하지 않음.
기존 DB 볼륨에는 아래처럼 추가 뷰를 적용함. 새 DB는 초기화 때 자동 적용됨.

```powershell
Get-Content -Raw -Encoding utf8 rdb/init/05_merchant_usage.sql |
  docker exec -i hybrid-ai-lab-rdb psql -X -1 -v ON_ERROR_STOP=1 -U cardlab -d cardlab
Get-Content -Raw -Encoding utf8 rdb/init/06_history_daily_usage.sql |
  docker exec -i hybrid-ai-lab-rdb psql -X -1 -v ON_ERROR_STOP=1 -U cardlab -d cardlab
```

RLS를 켜면 정책이 없는 역할은 0행이 됨. 전체 허용 정책을 가진 로그인 계정은 두지 않음.  
특히 `app_reader`에 전체 허용 정책을 더하면 같은 역할의 정책이 OR로 합쳐져  
`app` 뷰의 회원 격리가 풀리므로 금지함. 관리 계정 `cardlab`은 테이블 소유자라 RLS를 받지 않음.

검색기 계정은 세션 변수 `app.member_id` · `app.base_date` · `app.coverage_start`를
트랜잭션 안에서 지정해야 `app` 스키마 뷰가 행을 돌려줌. 지정하지 않으면 0행임.

```sql
-- sql_retriever_user로 접속했을 때
BEGIN READ ONLY;
SELECT set_config('app.member_id', 'M-5015', true),
       set_config('app.base_date', '2026-08-31', true),
       set_config('app.coverage_start', '2025-08-01', true);
SELECT card_ref, product_name, annual_fee FROM app.customer_cards ORDER BY card_ref;
COMMIT;
```

## 테이블

### public — 실습이 읽는 곳

| 테이블 | 행 수 | 설명 |
|--------|------|------|
| `member` | 600 | 회원. `member_id`는 **가명 ID**(`M-1042` 형식) |
| `product` | 64 | 카드 상품. `product_id`는 D2 자료 ID(`D2-C001`~`D2-C064`) |
| `product_annual_fee` | 133 | **카드 × 브랜드**별 연회비(기본·서비스·총연회비) |
| `card` | 1,200 | 발급 카드. `product_id` + `brand`로 연회비가 한 건으로 정해짐 |
| `merchant` | 80 | 가맹점 |
| `card_txn` | 78,802 | 거래. 취소 거래는 승인 금액과 합산하지 않음 |
| `delinquency` | 6,780 | 월별 연체 지표 |
| `lab_metadata` | 7 | 기준일·원자료 출처 등 데이터 기준 |

SQL 예제에서 컬럼을 직접 조회할 때는 아래 필드를 기준으로 살펴보면 됩니다.

금액은 정수 원 단위이고, 날짜는 `YYYY-MM-DD`, 기준월은 `YYYY-MM` 형식입니다.

| 테이블 | 주요 컬럼 |
|--------|-----------|
| `member` | `member_id`, `segment_id`, `join_date`, `age_band` |
| `card` | `card_id`, `member_id`, `product_id`, `brand`, `issue_date`, `status` |
| `product` | `product_id`, `product_name`, `effective_date`, `family_card_available` |
| `product_annual_fee` | `product_id`, `brand`, `base_fee`, `service_fee`, `total_fee` |
| `merchant` | `merchant_id`, `merchant_name`, `category` |
| `card_txn` | `txn_id`, `card_id`, `merchant_id`, `txn_date`, `amount`, `approval_code` |
| `delinquency` | `member_id`, `base_month`, `overdue_days`, `overdue_count_12m` |
| `lab_metadata` | `key`, `value` |

`delinquency`의 기본 키는 `member_id`와 `base_month`를 함께 사용합니다.

테이블 제약과 인덱스는 [스키마 정의](init/01_schema.sql)에서 확인할 수 있습니다.

### private — 실습이 읽지 못하는 곳

| 테이블 | 행 수 | 설명 |
|--------|------|------|
| `private.member_id_map` | 600 | 원 회원번호(8자리) ↔ 가명 ID 대응표 |

이 표는 개인정보보호법이 말하는 **"추가정보"(재식별 열쇠)** 에 해당함. 가명 ID와 같은 자리에
두면 가명처리의 의미가 사라지므로 스키마를 나누고 실습 계정에 권한을 주지 않음.
실제 운영에서는 스키마가 아니라 **저장소와 접근 권한 자체를 분리**해야 함.

```sql
-- sql_retriever_user로 실행하면 거부됨
SELECT * FROM private.member_id_map;   -- ERROR: permission denied for schema private
```

## 데이터 기준

| 항목 | 값 |
|------|-----|
| 회원 | 600명 (세그먼트 6종 × 100명) |
| 거래 기간 | 2025-08 ~ 2026-08 (13개월) |
| 기준일 | **2026-08-31** |
| 상품 시행일 | 2027-01-15 (D2 가상 시행일) |

상품 시행일이 기준일보다 **미래인 것은 의도한 설정**임. 시행일 조건으로 거르는 실습의
재료로 씀.

### SQL 예제의 조회 범위

SQL 예제는 2026-03-01부터 2026-08-31까지를 조회 기준일로 받으며, 기본 실행은 최근 6개월을 보여 줍니다.

고객의 모든 카드에서 `APPROVED` 거래만 합산하고 `CANCELLED` 거래는 제외합니다.

보유 상품은 `ACTIVE` 카드만 조회합니다. 연체 자료가 없으면 0건으로 단정하지 않고 `확인 필요`로 표시합니다.

다음 고객은 조회 결과의 의미를 확인할 때 사용할 수 있습니다.

| 고객 | 확인할 결과 |
|------|-------------|
| `M-1042` | 3월부터 8월까지 사용액이 점차 줄어듭니다. |
| `M-3099` | 8월 연체 자료가 없어 7월 자료가 반환되며, 현재 월은 `확인 필요`로 표시됩니다. |
| `M-3100` | 연체 자료가 전혀 없어 `확인 필요`로 표시됩니다. |

`M-1042`의 승인 거래 사용액은 다음과 같습니다.

| 2026년 월 | 사용액 |
|-----------|-------:|
| 3월 | 1,574,000원 |
| 4월 | 1,495,000원 |
| 5월 | 1,416,000원 |
| 6월 | 1,338,000원 |
| 7월 | 1,259,000원 |
| 8월 | 1,180,000원 |

2026년 5월 대비 8월 변화율은 약 -16.7%입니다.

취소 거래를 승인 거래에 섞으면 위 사용액과 일치하지 않습니다.

### 세그먼트

| ID | 이름 | 카드 수 | 특징 |
|----|------|--------|------|
| 1 | 신규 가입 | 1 | 2026년 가입, 일부는 미이용 |
| 2 | 장기 보유 | 2 | 사용액이 완만히 감소 |
| 3 | VIP | 2 | 고액 거래, 고연회비 카드 |
| 4 | 휴면 직전 | 1 | 사용액 급감, 일부는 최근 두 달 거래 없음 |
| 5 | 다중 카드 | 4 | 연회비 구간이 서로 다른 카드 4장 |
| 6 | 연회비 부담 | 2 | 고연회비 카드 |

### 실습용으로 일부러 심어 둔 것

| 장치 | 규모 | 쓰임 |
|------|------|------|
| 대표 고객 `M-1042` | 1명 | 사용액 1,574,000 → 1,180,000원(2026년 3~8월, 추가 거래 반영), 연체 없음 |
| 연체 지표가 아예 없는 회원 | 6명 | "0건은 연체 없음이 아니라 **확인 필요**" |
| 최신월(2026-08) 지표가 없는 회원 | 6명 | 같은 목적 |
| 정지(`SUSPENDED`) 카드 | 6장 | 상태 조건 필터 |
| 해지(`CLOSED`) 카드 | 6장 | 상태 조건 필터 |
| 취소(`CANCELLED`) 거래 | 1,727건 | 승인 금액과 섞지 않기 |

## 상품과 연회비를 읽는 법

연회비는 **카드 한 장에 하나가 아니라 브랜드마다 다름**. D2 원문 구조를 그대로 옮긴 것임.

```sql
-- 카드 한 장의 연회비는 product_id와 brand를 함께 맞춰야 나옴
SELECT p.product_name, c.brand, f.base_fee, f.service_fee, f.total_fee
FROM card c
JOIN product p USING (product_id)
JOIN product_annual_fee f ON f.product_id = c.product_id AND f.brand = c.brand
WHERE c.member_id = 'M-1042';
```

브랜드 라벨은 `국내전용` · `해외 A` · `해외 B` · `해외 C`이며, `D2-C054`만 예외로
`해외 A 모바일` · `해외 A 실물`로 나뉨.

가족카드 조건은 `product.family_card_rule`에 원문 문장 그대로 있고,
`product.family_card_available`(38종 운영 / 26종 미운영)로 걸러 쓸 수 있음.

## 데이터를 다시 만들 때

```bash
python rdb/extract_d2.py    # docs/D2_...pdf → data/d2_products.json (검증 포함)
python rdb/build_seed.py    # data/d2_products.json → init/02_seed.sql
docker compose -f rdb/compose.yml down -v
docker compose -f rdb/compose.yml up -d
```

`extract_d2.py`는 카드 64종·시행일·가족카드 조건·`기본+서비스=총연회비`를 모두 검사하고,
하나라도 어긋나면 파일을 쓰지 않고 멈춤. `build_seed.py`는 고정 난수를 쓰므로 몇 번을
돌려도 같은 데이터가 나옴.

| 파일 | 역할 |
|------|------|
| `compose.yml` | 컨테이너 정의 |
| `extract_d2.py` | D2 PDF에서 상품·연회비 추출 |
| `build_seed.py` | 합성 회원·카드·거래 생성 |
| `data/d2_products.json` | 추출 결과(상품 원천) |
| `init/01_schema.sql` | 스키마·권한 |
| `init/02_seed.sql` | 적재 데이터(생성물 — 직접 고치지 말 것) |
| `init/04_views_rls.sql` | 검색기용 논리 뷰·행 수준 보안·계정 (시드 이후에 실행되어야 함) |
| `init/05_merchant_usage.sql` | 카드·월·가맹점별 승인 집계 뷰 (04 이후 실행, 기존 DB 재적용 가능) |
| `init/06_history_daily_usage.sql` | 최근 12개 완료 월 연체 이력·최근 90일 일별 승인 집계 뷰 |

## 원자료

- `docs/D2_카드혜택안내_합성.pdf` — 카드 64종, 연회비. **상품 데이터의 유일한 출처**
- `docs/D1_개인회원표준약관_합성.pdf` — 회원 이용·해지 약관. 문서 검색 실습용이며 RDB에는 넣지 않음

카드별 **혜택 조건 270건**은 문장형이라 문서 검색(RAG)의 재료이므로 RDB에 넣지 않음.
"이 질문의 답이 표에 있나 문서에 있나"를 가르는 실습이 성립하려면 혜택은 문서에만 있어야 함.

## w2-3 SQLite 실습과의 관계

`w2-3/src/common`의 SQLite 실습은 **그대로 유지**되며 이 DB로 바뀌지 않음.
기본 회원·거래 생성 규칙은 같지만 PostgreSQL에는 D2 상품 64종과 상담 고객 12명의 추가 거래가 반영됨.
SQLite의 거래금액과 PostgreSQL의 상담 고객 거래금액은 같지 않을 수 있음.
