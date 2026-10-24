-- 정형 검색기(sql-retriever) 전용 논리 읽기 모델 — 뷰 + 행 수준 보안(RLS:Row Level Security)
-- 02_seed.sql, 03_consultation_transactions.sql 이후에 실행되어야 함(시드가 RLS에 막히지 않게 함).
--
-- 역할 분담
--   RLS : 회원 격리만 담당. member_id = current_setting('app.member_id')
--   뷰  : 기준일·6개월 창·컬럼 선택·card_ref 생성만 담당. 회원 조건은 쓰지 않음
-- 같은 조건을 두 곳에 두지 않으므로 한쪽만 고쳐서 어긋나는 사고를 막음.
--
-- 세션 변수 3개를 트랜잭션 안에서 set_config(..., true)로 지정해야 데이터가 보임.
--   app.member_id / app.base_date / app.coverage_start
-- 지정하지 않으면 current_setting(..., true)가 NULL을 반환하고 모든 비교가 거짓이 되어
-- 0행이 나옴. 기본 거부가 별도 설정 없이 성립함.

-- ---------------------------------------------------------------------------
-- 역할
-- ---------------------------------------------------------------------------
-- 뷰 소유자. 로그인할 수 없으며 RLS 정책이 이 역할에 걸림.
-- 테이블 소유자(cardlab)가 아니므로 RLS를 우회하지 못함.
CREATE ROLE app_reader NOLOGIN;

-- 검색기 서비스 계정. 원본 테이블 권한을 한 건도 갖지 않음.
CREATE ROLE sql_retriever_user LOGIN PASSWORD 'cardlab';

GRANT CONNECT ON DATABASE cardlab TO app_reader, sql_retriever_user;
GRANT USAGE ON SCHEMA public TO app_reader, sql_retriever_user;

GRANT SELECT ON
    public.member,
    public.card,
    public.card_txn,
    public.delinquency,
    public.product,
    public.product_annual_fee
TO app_reader;

-- 데이터 기준일·거래 제공 기간은 회원과 무관한 메타데이터이므로 서비스가 직접 읽음.
GRANT SELECT ON public.lab_metadata TO sql_retriever_user;

-- ---------------------------------------------------------------------------
-- 행 수준 보안 — 회원 격리
-- ---------------------------------------------------------------------------
-- 주의: RLS를 켜면 소유자가 아닌 모든 역할이 정책의 적용을 받음. 정책이 없으면 0행이 됨.
-- 소유자 cardlab은 FORCE ROW LEVEL SECURITY를 켜지 않았으므로 그대로 전체를 봄(관리 계정).
-- 원본 전체를 읽어야 하는 오프라인 도구는 cardlab을 씀. app_reader에 전체 허용 정책을 더하지 않음
-- — 같은 역할의 허용 정책은 OR로 합쳐져 app 뷰의 회원 격리가 풀리기 때문임.

ALTER TABLE public.member ENABLE ROW LEVEL SECURITY;
CREATE POLICY member_session_scope ON public.member
    FOR SELECT TO app_reader
    USING (member_id = NULLIF(current_setting('app.member_id', true), ''));

ALTER TABLE public.card ENABLE ROW LEVEL SECURITY;
CREATE POLICY card_session_scope ON public.card
    FOR SELECT TO app_reader
    USING (member_id = NULLIF(current_setting('app.member_id', true), ''));

-- card_txn에는 member_id가 없으므로 카드를 거쳐 회원을 확인함.
-- 안쪽 card 조회에도 위 card 정책이 그대로 적용되어 판정이 어긋나지 않음.
ALTER TABLE public.card_txn ENABLE ROW LEVEL SECURITY;
CREATE POLICY card_txn_session_scope ON public.card_txn
    FOR SELECT TO app_reader
    USING (EXISTS (
        SELECT 1
        FROM public.card AS scoped_card
        WHERE scoped_card.card_id = card_txn.card_id
          AND scoped_card.member_id = NULLIF(current_setting('app.member_id', true), '')
    ));

ALTER TABLE public.delinquency ENABLE ROW LEVEL SECURITY;
CREATE POLICY delinquency_session_scope ON public.delinquency
    FOR SELECT TO app_reader
    USING (member_id = NULLIF(current_setting('app.member_id', true), ''));

-- product / product_annual_fee / merchant / lab_metadata는 회원별 자료가 아니므로 RLS를 걸지 않음.

-- ---------------------------------------------------------------------------
-- 스키마 — 공개(app)와 내부(app_internal)를 분리
-- ---------------------------------------------------------------------------
CREATE SCHEMA app          AUTHORIZATION app_reader;
CREATE SCHEMA app_internal AUTHORIZATION app_reader;
COMMENT ON SCHEMA app IS
    'NL2SQL이 볼 수 있는 논리 읽기 모델. 원본 카드ID를 포함하지 않음.';
COMMENT ON SCHEMA app_internal IS
    '서비스 코드 전용. 원본 카드ID와 조립용 중간 뷰가 있어 NL2SQL에 노출하지 않음.';

-- 아래 뷰는 app_reader가 소유해야 함. 소유자 권한으로 실행되어야
-- 서비스 계정에 원본 테이블 권한을 주지 않고도 조회가 되기 때문임.
SET ROLE app_reader;

-- ---------------------------------------------------------------------------
-- 요청 범위 — 시간 범위 세션 변수를 한 행으로 노출
-- ---------------------------------------------------------------------------
-- 회원ID는 두지 않음. 회원 격리는 RLS가 전부 맡으므로 뷰가 회원을 알 필요가 없음.
-- 뷰가 아는 것은 시간 범위뿐임.
--
-- NULLIF가 필요한 이유: set_config(..., true)로 넣은 값은 트랜잭션이 끝나면
-- NULL이 아니라 빈 문자열로 되돌아감. 커넥션을 재사용하면 ''::date 형변환 오류가 나므로
-- 빈 문자열을 NULL로 바꿔 "값 없음"과 같게 취급함.
CREATE VIEW app_internal.request_scope WITH (security_barrier = true) AS
SELECT
    NULLIF(current_setting('app.base_date', true), '')::date      AS base_date,
    NULLIF(current_setting('app.coverage_start', true), '')::date AS coverage_start;

-- ---------------------------------------------------------------------------
-- 회원 — 기준일 필터 없음
-- 회원 존재 확인과 가입일 검증용. 기준일로 거르면 "없는 회원"과
-- "가입 전 기준일"을 구분할 수 없어 별도로 둠.
-- ---------------------------------------------------------------------------
CREATE VIEW app_internal.member_basic WITH (security_barrier = true) AS
SELECT m.member_id, m.join_date, m.age_band
FROM public.member AS m;

CREATE VIEW app.customer_profile WITH (security_barrier = true) AS
SELECT m.join_date, m.age_band
FROM public.member AS m
CROSS JOIN app_internal.request_scope AS scope
WHERE m.join_date <= scope.base_date;

-- ---------------------------------------------------------------------------
-- 카드 — 원본 card_id는 app_internal에만 둠
-- card_ref는 RLS로 좁혀진 회원의 카드 안에서만 번호를 매김.
-- ---------------------------------------------------------------------------
CREATE VIEW app_internal.customer_cards_full WITH (security_barrier = true) AS
SELECT
    c.card_id,
    'CARD_' || lpad(row_number() OVER (ORDER BY c.card_id)::text, 3, '0') AS card_ref,
    c.product_id,
    p.product_name,
    c.brand,
    c.issue_date,
    c.status AS current_status,
    p.effective_date AS product_effective_date,
    (p.effective_date <= scope.base_date) AS is_product_effective_on_base_date,
    fee.total_fee AS annual_fee
FROM public.card AS c
CROSS JOIN app_internal.request_scope AS scope
JOIN public.product AS p
  ON p.product_id = c.product_id
JOIN public.product_annual_fee AS fee
  ON fee.product_id = c.product_id AND fee.brand = c.brand
WHERE c.issue_date <= scope.base_date;

CREATE VIEW app.customer_cards WITH (security_barrier = true) AS
SELECT
    card_ref,
    product_id,
    product_name,
    brand,
    issue_date,
    current_status,
    product_effective_date,
    is_product_effective_on_base_date,
    annual_fee
FROM app_internal.customer_cards_full;

-- ---------------------------------------------------------------------------
-- 월 집계 — 최근 6개월, 거래 제공 시작월 이전은 만들지 않음
-- ---------------------------------------------------------------------------
CREATE VIEW app_internal.usage_months WITH (security_barrier = true) AS
SELECT month_start::date AS month_start
FROM app_internal.request_scope AS scope
CROSS JOIN LATERAL generate_series(
    greatest(
        date_trunc('month', scope.base_date) - INTERVAL '5 months',
        date_trunc('month', scope.coverage_start)
    ),
    date_trunc('month', scope.base_date),
    INTERVAL '1 month'
) AS month_start;

CREATE VIEW app.monthly_usage WITH (security_barrier = true) AS
SELECT
    cards.card_ref,
    to_char(months.month_start, 'YYYY-MM') AS month,
    greatest(months.month_start, cards.issue_date)::date AS period_start,
    least(
        (months.month_start + INTERVAL '1 month - 1 day')::date,
        scope.base_date
    ) AS period_end,
    coalesce(sum(txn.amount), 0)::bigint AS approved_amount,
    count(txn.txn_id)::integer AS transaction_count
FROM app_internal.customer_cards_full AS cards
CROSS JOIN app_internal.request_scope AS scope
CROSS JOIN app_internal.usage_months AS months
LEFT JOIN public.card_txn AS txn
  ON txn.card_id = cards.card_id
 AND txn.approval_code = 'APPROVED'
 AND txn.txn_date >= greatest(months.month_start, cards.issue_date)::date
 AND txn.txn_date <= least(
     (months.month_start + INTERVAL '1 month - 1 day')::date,
     scope.base_date
 )
WHERE cards.issue_date <= least(
    (months.month_start + INTERVAL '1 month - 1 day')::date,
    scope.base_date
)
GROUP BY cards.card_ref, months.month_start, cards.issue_date, scope.base_date;

-- ---------------------------------------------------------------------------
-- 연체 — 기준일 이전에 완료된 월 가운데 가장 최근 한 건
-- ---------------------------------------------------------------------------
CREATE VIEW app.customer_delinquency WITH (security_barrier = true) AS
SELECT
    d.base_month,
    (
        to_date(d.base_month || '-01', 'YYYY-MM-DD')
        + INTERVAL '1 month - 1 day'
    )::date AS as_of_date,
    d.overdue_amount,
    d.overdue_days,
    d.overdue_count_12m
FROM public.delinquency AS d
CROSS JOIN app_internal.request_scope AS scope
WHERE (
    to_date(d.base_month || '-01', 'YYYY-MM-DD')
    + INTERVAL '1 month - 1 day'
)::date <= scope.base_date
ORDER BY d.base_month DESC
LIMIT 1;

RESET ROLE;

-- ---------------------------------------------------------------------------
-- 서비스 계정 권한 — 뷰만 허용
-- app_internal.request_scope와 usage_months는 주지 않음. 조립용 중간 뷰이며,
-- 이를 참조하는 바깥 뷰가 소유자 권한으로 실행되므로 필요하지 않음.
-- ---------------------------------------------------------------------------
GRANT USAGE ON SCHEMA app, app_internal TO sql_retriever_user;
GRANT SELECT ON
    app.customer_profile,
    app.customer_cards,
    app.monthly_usage,
    app.customer_delinquency
TO sql_retriever_user;
GRANT SELECT ON
    app_internal.customer_cards_full,
    app_internal.member_basic
TO sql_retriever_user;
