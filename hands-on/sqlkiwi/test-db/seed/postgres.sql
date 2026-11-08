-- sqlkiwi 시험용 PostgreSQL 데이터
CREATE SCHEMA shop;

CREATE TABLE shop.customers (
  id         serial PRIMARY KEY,
  name       varchar(50) NOT NULL,
  email      varchar(100) UNIQUE,
  joined_at  timestamp NOT NULL DEFAULT now()
);

CREATE TABLE shop.orders (
  id          serial PRIMARY KEY,
  customer_id integer NOT NULL REFERENCES shop.customers(id),
  amount      numeric(10, 2) NOT NULL,
  memo        text,
  ordered_at  timestamp NOT NULL DEFAULT now()
);
CREATE INDEX orders_customer_idx ON shop.orders(customer_id);

CREATE VIEW shop.customer_totals AS
  SELECT c.id, c.name, coalesce(sum(o.amount), 0) AS total
  FROM shop.customers c LEFT JOIN shop.orders o ON o.customer_id = c.id
  GROUP BY c.id, c.name;

INSERT INTO shop.customers(name, email)
  SELECT '고객' || g, 'user' || g || '@example.com' FROM generate_series(1, 30) AS g;

-- 결과 그리드의 "더 가져오기"를 시험하려고 행을 넉넉히 넣음(500행)
INSERT INTO shop.orders(customer_id, amount, memo)
  SELECT (g % 30) + 1, round((random() * 100000)::numeric, 2),
         CASE WHEN g % 7 = 0 THEN NULL ELSE '주문 ' || g END
  FROM generate_series(1, 500) AS g;
