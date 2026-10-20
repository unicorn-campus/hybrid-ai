"""외부 설정과 SQL 파일에서 논리 읽기 모델 조회문을 불러옵니다.

논리 뷰와 원본 테이블 관계는 ``sql/query_config.json``에서 관리하고,
실행 SQL은 같은 디렉터리의 개별 ``.sql`` 파일에서 관리합니다.
"""

import json
from pathlib import Path
import re
from typing import Any


SQL_DIRECTORY = Path(__file__).with_name("sql")
CONFIG_PATH = SQL_DIRECTORY / "query_config.json"


def _load_config() -> dict[str, Any]:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"SQL 설정 파일을 읽을 수 없습니다: {CONFIG_PATH}") from error
    if not isinstance(config, dict):
        raise RuntimeError("SQL 설정 파일의 최상위 값은 객체여야 합니다.")
    return config


def _read_sql(config: dict[str, Any], name: str) -> str:
    try:
        filename = config["sql_files"][name]
    except (KeyError, TypeError) as error:
        raise RuntimeError(f"SQL 파일 설정이 없습니다: {name}") from error
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise RuntimeError(f"SQL 파일 이름이 올바르지 않습니다: {name}")
    path = SQL_DIRECTORY / filename
    try:
        sql = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError(f"SQL 파일을 읽을 수 없습니다: {path}") from error
    if not sql:
        raise RuntimeError(f"SQL 파일이 비어 있습니다: {path}")
    return sql


_CONFIG = _load_config()

try:
    _SCOPE_SETTINGS = _CONFIG["scope_settings"]
    MEMBER_SETTING = str(_SCOPE_SETTINGS["member"])
    BASE_DATE_SETTING = str(_SCOPE_SETTINGS["base_date"])
    COVERAGE_START_SETTING = str(_SCOPE_SETTINGS["coverage_start"])
    LOGICAL_SCHEMA_NAME = str(_CONFIG["logical_schema"])
    _VIEW_CONFIG = _CONFIG["logical_views"]
    LOGICAL_VIEWS = tuple(str(item["name"]) for item in _VIEW_CONFIG)
    LOGICAL_SCHEMA = {
        str(item["name"]): tuple(str(column) for column in item["columns"])
        for item in _VIEW_CONFIG
    }
    LOGICAL_VIEW_SOURCES = {
        str(item["name"]): tuple(str(table) for table in item["source_tables"])
        for item in _VIEW_CONFIG
    }
except (KeyError, TypeError) as error:
    raise RuntimeError("SQL 설정 파일의 필수 항목을 확인해 주세요.") from error

if not LOGICAL_VIEWS or len(LOGICAL_VIEWS) != len(set(LOGICAL_VIEWS)):
    raise RuntimeError("논리 뷰 설정은 중복 없이 한 개 이상 필요합니다.")
if re.fullmatch(r"[a-z_][a-z0-9_]*", LOGICAL_SCHEMA_NAME) is None:
    raise RuntimeError("논리 스키마 이름이 올바르지 않습니다.")
if any(not LOGICAL_SCHEMA[name] for name in LOGICAL_VIEWS):
    raise RuntimeError("각 논리 뷰에는 컬럼이 한 개 이상 필요합니다.")

SCOPE_SETTINGS = (MEMBER_SETTING, BASE_DATE_SETTING, COVERAGE_START_SETTING)

MEMBER_SELECT = _read_sql(_CONFIG, "member_select")
METADATA_SELECT = _read_sql(_CONFIG, "metadata_select")
PROFILE_SELECT = _read_sql(_CONFIG, "profile_select")
CARDS_SELECT = _read_sql(_CONFIG, "cards_select")
USAGE_SELECT = _read_sql(_CONFIG, "usage_select")
DELINQUENCY_SELECT = _read_sql(_CONFIG, "delinquency_select")
SEARCH_METADATA_SELECT = _read_sql(_CONFIG, "search_metadata_select")
_GUARDED_QUERY_TEMPLATE = _read_sql(_CONFIG, "guarded_query")
SCHEMA_COLUMNS_SELECT = _read_sql(_CONFIG, "schema_columns_select")


def guarded_query(validated_sql: str) -> str:
    """검증된 논리 SQL에 외부 템플릿으로 저장소 상한 101행을 적용합니다."""

    return _GUARDED_QUERY_TEMPLATE.format(validated_sql=validated_sql.strip())
