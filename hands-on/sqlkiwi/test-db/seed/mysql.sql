-- sqlkiwi 시험용 MySQL 데이터
-- 초기화 스크립트를 읽는 mysql 클라이언트의 기본 문자셋이 latin1이라 한글이 이중 인코딩되지 않게 지정함
SET NAMES utf8mb4;
USE kiwi;

CREATE TABLE customers (
  id         INT AUTO_INCREMENT PRIMARY KEY,
  name       VARCHAR(50) NOT NULL,
  email      VARCHAR(100) UNIQUE,
  joined_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) DEFAULT CHARSET = utf8mb4;

CREATE TABLE orders (
  id          INT AUTO_INCREMENT PRIMARY KEY,
  customer_id INT NOT NULL,
  amount      DECIMAL(10, 2) NOT NULL,
  memo        TEXT,
  ordered_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX orders_customer_idx (customer_id),
  CONSTRAINT orders_customer_fk FOREIGN KEY (customer_id) REFERENCES customers(id)
) DEFAULT CHARSET = utf8mb4;

CREATE VIEW customer_totals AS
  SELECT c.id, c.name, COALESCE(SUM(o.amount), 0) AS total
  FROM customers c LEFT JOIN orders o ON o.customer_id = c.id
  GROUP BY c.id, c.name;

-- 1부터 500까지 숫자를 만드는 재귀 CTE로 시험 행을 넣음
INSERT INTO customers(name, email)
  WITH RECURSIVE g(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM g WHERE n < 30)
  SELECT CONCAT('고객', n), CONCAT('user', n, '@example.com') FROM g;

SET SESSION cte_max_recursion_depth = 1000;
INSERT INTO orders(customer_id, amount, memo)
  WITH RECURSIVE g(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM g WHERE n < 500)
  SELECT (n % 30) + 1, ROUND(RAND() * 100000, 2),
         CASE WHEN n % 7 = 0 THEN NULL ELSE CONCAT('주문 ', n) END
  FROM g;
