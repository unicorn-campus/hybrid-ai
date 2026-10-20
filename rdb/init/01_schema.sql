-- 하이브리드 AI 실습 공통 정형 DB 스키마
-- 교육용 합성 데이터 전용. 금액 단위: 원, 날짜: ISO 8601.
-- 상품·연회비는 docs/D2_카드혜택안내_합성.pdf(가상 시행일 2027-01-15)에서 추출함.
-- 거래·회원은 기준일 2026-08-31로 생성함. 상품 시행일이 기준일보다 미래인 것은
-- 의도한 설정이며, 시행일 필터 실습의 재료로 씀.

-- ---------------------------------------------------------------------------
-- 스키마: 공개(public)와 재식별 열쇠(private)를 분리함
-- ---------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS private;
COMMENT ON SCHEMA private IS
    '가명 ID의 재식별 열쇠(추가정보)만 두는 스키마. 실습 계정은 접근할 수 없음.';

-- ---------------------------------------------------------------------------
-- 회원
-- ---------------------------------------------------------------------------
CREATE TABLE member (
    member_id   text     PRIMARY KEY,
    segment_id  smallint NOT NULL CHECK (segment_id BETWEEN 1 AND 6),
    join_date   date     NOT NULL,
    age_band    text     NOT NULL
);
COMMENT ON TABLE member IS '회원. member_id는 가명 ID이며 원 회원번호는 private.member_id_map에만 있음.';
COMMENT ON COLUMN member.segment_id IS '1 신규 가입 / 2 장기 보유 / 3 VIP / 4 휴면 직전 / 5 다중 카드 / 6 연회비 부담';
COMMENT ON COLUMN member.age_band IS '생년월일을 상위 개념으로 뭉갠 값(모호화).';

-- ---------------------------------------------------------------------------
-- 상품과 연회비 (D2 원문 구조 유지 — 연회비는 카드 x 브랜드 단위)
-- ---------------------------------------------------------------------------
CREATE TABLE product (
    product_id            text    PRIMARY KEY,
    product_name          text    NOT NULL,
    effective_date        date    NOT NULL,
    family_card_available boolean NOT NULL,
    family_card_rule      text    NOT NULL
);
COMMENT ON TABLE product IS 'D2 카드 64종. product_id는 D2 자료 ID(D2-C001~D2-C064)와 같음.';
COMMENT ON COLUMN product.effective_date IS 'D2 가상 시행일. 거래 기준일(2026-08-31)보다 미래임.';
COMMENT ON COLUMN product.family_card_available IS 'D2 가족카드 문구가 "가족카드 미운영"이면 false.';
COMMENT ON COLUMN product.family_card_rule IS 'D2 원문 가족카드 조건 문장 그대로.';

CREATE TABLE product_annual_fee (
    product_id  text    NOT NULL REFERENCES product(product_id),
    brand       text    NOT NULL,
    base_fee    integer NOT NULL CHECK (base_fee >= 0),
    service_fee integer NOT NULL CHECK (service_fee >= 0),
    total_fee   integer NOT NULL CHECK (total_fee >= 0),
    PRIMARY KEY (product_id, brand),
    CHECK (base_fee + service_fee = total_fee)
);
COMMENT ON TABLE product_annual_fee IS
    '브랜드·발급 방식별 연회비. D2에서 카드마다 1~3행이며 총 133행임.';
COMMENT ON COLUMN product_annual_fee.brand IS
    '국내전용 / 해외 A / 해외 B / 해외 C / 해외 A 모바일 / 해외 A 실물';

-- ---------------------------------------------------------------------------
-- 가맹점·카드·거래
-- ---------------------------------------------------------------------------
CREATE TABLE merchant (
    merchant_id   text PRIMARY KEY,
    merchant_name text NOT NULL,
    category      text NOT NULL
);

CREATE TABLE card (
    card_id    text NOT NULL PRIMARY KEY,
    member_id  text NOT NULL REFERENCES member(member_id),
    product_id text NOT NULL,
    brand      text NOT NULL,
    issue_date date NOT NULL,
    status     text NOT NULL CHECK (status IN ('ACTIVE', 'CLOSED', 'SUSPENDED')),
    -- 발급된 카드는 반드시 연회비가 정의된 브랜드여야 함.
    FOREIGN KEY (product_id, brand) REFERENCES product_annual_fee(product_id, brand)
);
COMMENT ON COLUMN card.brand IS '발급 브랜드. 이 값이 있어야 연회비가 한 건으로 정해짐.';

CREATE TABLE card_txn (
    txn_id        text    PRIMARY KEY,
    card_id       text    NOT NULL REFERENCES card(card_id),
    merchant_id   text    NOT NULL REFERENCES merchant(merchant_id),
    txn_date      date    NOT NULL,
    amount        integer NOT NULL CHECK (amount > 0),
    approval_code text    NOT NULL CHECK (approval_code IN ('APPROVED', 'CANCELLED'))
);
COMMENT ON TABLE card_txn IS '취소 거래는 취소된 승인 시도 자체이며 APPROVED 금액과 합산하지 않음.';

-- ---------------------------------------------------------------------------
-- 연체 지표
-- ---------------------------------------------------------------------------
CREATE TABLE delinquency (
    member_id         text    NOT NULL REFERENCES member(member_id),
    base_month        char(7) NOT NULL CHECK (base_month ~ '^\d{4}-\d{2}$'),
    overdue_days      integer NOT NULL CHECK (overdue_days BETWEEN 0 AND 31),
    overdue_count_12m integer NOT NULL CHECK (overdue_count_12m BETWEEN 0 AND 12),
    overdue_amount    integer NOT NULL CHECK (overdue_amount >= 0),
    PRIMARY KEY (member_id, base_month),
    CHECK ((overdue_days = 0 AND overdue_amount = 0) OR
           (overdue_days > 0 AND overdue_amount > 0 AND overdue_count_12m > 0))
);
COMMENT ON COLUMN delinquency.overdue_count_12m IS '최근 12개월 중 연체 발생 월 수(월 1건 가정).';

-- ---------------------------------------------------------------------------
-- 재식별 열쇠 — 분리 보관
-- ---------------------------------------------------------------------------
CREATE TABLE private.member_id_map (
    source_member_no char(8) PRIMARY KEY CHECK (source_member_no ~ '^\d{8}$'),
    member_id        text    NOT NULL UNIQUE REFERENCES public.member(member_id)
);
COMMENT ON TABLE private.member_id_map IS
    '원 회원번호와 가명 ID의 대응표. 개인정보보호법상 "추가정보"에 해당하므로 '
    '실습 계정에 권한을 주지 않고, 실제 운영에서는 저장소 자체를 분리해야 함.';

-- ---------------------------------------------------------------------------
-- 메타데이터 (재생성 없이 데이터 기준을 확인할 수 있게 함)
-- ---------------------------------------------------------------------------
CREATE TABLE lab_metadata (
    key   text PRIMARY KEY,
    value text NOT NULL
);

-- ---------------------------------------------------------------------------
-- 색인
-- ---------------------------------------------------------------------------
CREATE INDEX idx_member_segment  ON member(segment_id);
CREATE INDEX idx_card_member     ON card(member_id, status);
CREATE INDEX idx_card_product    ON card(product_id, brand);
CREATE INDEX idx_txn_card_date   ON card_txn(card_id, txn_date, approval_code);
CREATE INDEX idx_txn_merchant    ON card_txn(merchant_id);
CREATE INDEX idx_fee_total       ON product_annual_fee(total_fee);

-- ---------------------------------------------------------------------------
-- private 스키마 — 관리 계정(cardlab) 외에는 접근 불가
-- ---------------------------------------------------------------------------
-- 로그인 계정은 04_views_rls.sql의 sql_retriever_user 하나뿐이며 public 원본 테이블 권한도 없음.
-- private에는 USAGE조차 주지 않음. 아래 REVOKE는 기본값을 명시적으로 못 박는 것임.
REVOKE ALL ON SCHEMA private FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA private FROM PUBLIC;
