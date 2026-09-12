from __future__ import annotations

import sqlite3
import re
from pathlib import Path
from typing import Any


DEMO_DATE = "2026-09-04"


class OnetouchRepository:
    """Replaceable read-only adapter for the 원터치 quotation Data Hub demo."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.docs_dir = Path(__file__).resolve().parents[1] / "sample_docs"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS quote_requests (
                    quote_id TEXT PRIMARY KEY, drawing_id TEXT, customer TEXT,
                    product_family TEXT, requested_qty INTEGER, received_at TEXT,
                    due_at TEXT, priority TEXT, status TEXT
                );
                CREATE TABLE IF NOT EXISTS drawings (
                    drawing_id TEXT PRIMARY KEY, file_name TEXT, revision TEXT,
                    parse_method TEXT, parse_status TEXT, overall_confidence REAL,
                    exception_reason TEXT, reviewed_by TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS manufacturing_features (
                    drawing_id TEXT PRIMARY KEY, length_mm REAL, width_mm REAL,
                    height_mm REAL, thickness_mm REAL, material TEXT,
                    round_holes INTEGER, slots INTEGER, hole_spacing_mm REAL,
                    feature_confidence REAL, provenance TEXT
                );
                CREATE TABLE IF NOT EXISTS bom_items (
                    bom_id TEXT PRIMARY KEY, quote_id TEXT, item_name TEXT,
                    specification TEXT, quantity REAL, unit TEXT, unit_cost_krw REAL,
                    amount_krw REAL, generation_method TEXT
                );
                CREATE TABLE IF NOT EXISTS routings (
                    route_id TEXT PRIMARY KEY, quote_id TEXT, sequence_no INTEGER,
                    process_name TEXT, equipment TEXT, setup_min REAL, run_min REAL,
                    work_cost_krw REAL, generation_method TEXT
                );
                CREATE TABLE IF NOT EXISTS cost_estimates (
                    quote_id TEXT PRIMARY KEY, material_cost_krw REAL,
                    processing_cost_krw REAL, setup_cost_krw REAL,
                    overhead_krw REAL, estimated_total_krw REAL,
                    confidence REAL, review_route TEXT, model_name TEXT,
                    model_status TEXT, top_factors TEXT, calculated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS quote_history (
                    history_id TEXT PRIMARY KEY, product_family TEXT,
                    length_mm REAL, thickness_mm REAL, holes INTEGER, slots INTEGER,
                    quantity INTEGER, quoted_total_krw REAL, actual_cost_krw REAL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS material_inventory (
                    material_code TEXT PRIMARY KEY, material_name TEXT,
                    specification TEXT, available_kg REAL, reserved_kg REAL,
                    safety_stock_kg REAL, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS approval_queue (
                    approval_id TEXT PRIMARY KEY, quote_id TEXT, decision TEXT,
                    owner_role TEXT, evidence_status TEXT, approval_status TEXT,
                    requested_at TEXT
                );
                CREATE TABLE IF NOT EXISTS order_feedback (
                    order_no TEXT PRIMARY KEY, quote_id TEXT, production_status TEXT,
                    planned_cost_krw REAL, actual_cost_krw REAL, variance_pct REAL,
                    feedback_status TEXT, updated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    document_id TEXT PRIMARY KEY, title TEXT, filename TEXT UNIQUE,
                    revision TEXT, owner TEXT, effective_date TEXT, status TEXT,
                    keywords TEXT, body TEXT, source_label TEXT
                );
                CREATE TABLE IF NOT EXISTS rules (
                    rule_id TEXT PRIMARY KEY, name TEXT, source_table TEXT,
                    condition TEXT, owner TEXT, action TEXT,
                    source_document TEXT, revision TEXT, status TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (
                    setting_key TEXT PRIMARY KEY, setting_value TEXT
                );
                """
            )
            if connection.execute("SELECT COUNT(*) AS count FROM quote_requests").fetchone()["count"] == 0:
                self._seed(connection)
            self._seed_knowledge(connection)

    @staticmethod
    def _seed(connection: sqlite3.Connection) -> None:
        connection.executemany("INSERT INTO quote_requests VALUES (?,?,?,?,?,?,?,?,?)", [
            ("QT-260904-001", "DWG-260904-001", "거래처 A", "표준 잔넬", 1200, "2026-09-04 08:20", "2026-09-04 14:00", "긴급", "승인대기"),
            ("QT-260904-002", "DWG-260904-002", "거래처 B", "주문형 잔넬", 600, "2026-09-04 09:10", "2026-09-05 10:00", "일반", "담당자 검토"),
            ("QT-260904-003", "DWG-260904-003", "거래처 C", "C형강", 350, "2026-09-04 10:40", "2026-09-05 15:00", "일반", "수작업 전환"),
        ])
        connection.executemany("INSERT INTO drawings VALUES (?,?,?,?,?,?,?,?,?)", [
            ("DWG-260904-001", "channel_A_rev2.dwg", "R2", "CAD Parsing+OCR", "추출완료", 0.97, None, None, "2026-09-04 08:24"),
            ("DWG-260904-002", "custom_slot_B.pdf", "R1", "YOLOv8+OCR", "검토필요", 0.87, "슬롯 간격 치수 중복", None, "2026-09-04 09:18"),
            ("DWG-260904-003", "c_section_scan_C.pdf", "미확인", "YOLOv8+OCR", "수작업전환", 0.74, "재질·두께 문자 인식 불확실", None, "2026-09-04 10:52"),
        ])
        connection.executemany("INSERT INTO manufacturing_features VALUES (?,?,?,?,?,?,?,?,?,?,?)", [
            ("DWG-260904-001", 3000, 100, 50, 2.3, "SPHC", 8, 2, 300, 0.97, "demo_data"),
            ("DWG-260904-002", 4200, 120, 60, 3.2, "SS400", 12, 6, 250, 0.87, "demo_data"),
            ("DWG-260904-003", 2500, 80, 40, 1.6, "미확인", 4, 0, 500, 0.74, "demo_data"),
        ])
        connection.executemany("INSERT INTO bom_items VALUES (?,?,?,?,?,?,?,?,?)", [
            ("BOM-001-1", "QT-260904-001", "열연코일", "SPHC 2.3T", 9780, "kg", 1120, 10953600, "Rule/GNN 후보"),
            ("BOM-001-2", "QT-260904-001", "포장자재", "밴딩·라벨", 1200, "EA", 180, 216000, "Rule"),
            ("BOM-002-1", "QT-260904-002", "구조용강", "SS400 3.2T", 8640, "kg", 1280, 11059200, "Rule/GNN 후보"),
            ("BOM-003-1", "QT-260904-003", "코일", "재질 확인 필요", 1680, "kg", 0, 0, "수작업 확인"),
        ])
        connection.executemany("INSERT INTO routings VALUES (?,?,?,?,?,?,?,?,?)", [
            ("RT-001-1", "QT-260904-001", 10, "피딩·롤포밍", "피더/롤포밍기", 35, 420, 1260000, "Rule"),
            ("RT-001-2", "QT-260904-001", 20, "타공", "타공기", 20, 190, 570000, "Feature Rule"),
            ("RT-001-3", "QT-260904-001", 30, "절단·포장", "절단기/포장", 15, 160, 480000, "Rule"),
            ("RT-002-1", "QT-260904-002", 10, "피딩·롤포밍", "피더/롤포밍기", 45, 330, 990000, "Rule"),
            ("RT-002-2", "QT-260904-002", 20, "홀·슬롯 가공", "타공기", 40, 260, 780000, "Feature Rule"),
            ("RT-003-1", "QT-260904-003", 10, "공정 검토", "미확정", 0, 0, 0, "수작업 확인"),
        ])
        connection.executemany("INSERT INTO cost_estimates VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
            ("QT-260904-001", 11169600, 2310000, 320000, 1380000, 15179600, 0.97, "자동 산출 후보·담당자 승인", "XGBoost+표준원가식", "시제품 데모·미검증", "재질·중량·수량·타공수", "2026-09-04 08:26"),
            ("QT-260904-002", 11059200, 1770000, 410000, 1320000, 14559200, 0.87, "담당자 확인·승인", "XGBoost+표준원가식", "시제품 데모·미검증", "재질·두께·슬롯수·설정시간", "2026-09-04 09:21"),
            ("QT-260904-003", 0, 0, 0, 0, 0, 0.74, "수작업 견적 전환", "미적용", "입력 불충분", "재질·두께 불확실", "2026-09-04 10:55"),
        ])
        connection.executemany("INSERT INTO quote_history VALUES (?,?,?,?,?,?,?,?,?,?)", [
            ("HIS-001", "표준 잔넬", 3000, 2.3, 8, 2, 1000, 12800000, 12450000, "2026-07-15"),
            ("HIS-002", "표준 잔넬", 3000, 2.3, 6, 2, 1500, 18400000, 17980000, "2026-08-02"),
            ("HIS-003", "주문형 잔넬", 4000, 3.2, 12, 4, 500, 11900000, 11650000, "2026-08-18"),
        ])
        connection.executemany("INSERT INTO material_inventory VALUES (?,?,?,?,?,?,?)", [
            ("MAT-SPHC-23", "열연코일", "SPHC 2.3T", 12800, 4200, 3000, "2026-09-04 08:00"),
            ("MAT-SS400-32", "구조용강", "SS400 3.2T", 9200, 6500, 3500, "2026-09-04 08:00"),
            ("MAT-UNKNOWN", "재질 미확인 코일", "확인 필요", 0, 0, 0, "2026-09-04 08:00"),
        ])
        connection.executemany("INSERT INTO approval_queue VALUES (?,?,?,?,?,?,?)", [
            ("APR-001", "QT-260904-001", "견적금액·납기 승인", "영업·견적 책임자", "도면·BOM·Routing·원가 근거 준비", "승인대기", "2026-09-04 08:30"),
            ("APR-002", "QT-260904-002", "슬롯 치수 확인 및 견적 승인", "설계·견적 담당자", "도면 예외 검토 필요", "검토대기", "2026-09-04 09:25"),
            ("APR-003", "QT-260904-003", "수작업 견적 전환", "견적 담당자", "재질·두께 원본 확인 필요", "조치대기", "2026-09-04 11:00"),
        ])
        connection.executemany("INSERT INTO order_feedback VALUES (?,?,?,?,?,?,?,?)", [
            ("SO-260801", "QT-HIST-801", "생산완료", 12500000, 12900000, 3.2, "학습후보", "2026-08-25"),
            ("SO-260815", "QT-HIST-815", "생산완료", 11800000, 11500000, -2.54, "검증완료", "2026-09-01"),
        ])

    def _seed_knowledge(self, connection: sqlite3.Connection) -> None:
        metadata = {
            "cad_feature_standard.md": ("OT-KB-001", "CAD 제조 Feature 추출 기준", "설계·견적", "도면, 개정, OCR, 신뢰도"),
            "bom_routing_standard.md": ("OT-KB-002", "BOM·공정 Routing 생성 기준", "생산기술", "BOM, Routing, 공정, 소재"),
            "costing_approval_policy.md": ("OT-KB-003", "견적 원가·승인 정책", "영업·견적", "원가, 신뢰도, 승인, 수작업"),
            "model_validation_guide.md": ("OT-KB-004", "CAD 견적 모델 검증 가이드", "DX·품질", "모델, 검증, KPI, SHAP"),
            "drawing_change_control.md": ("OT-KB-005", "도면 개정·변경관리 절차", "설계", "도면, 변경, 개정, 재견적"),
            "material_shortage_response.md": ("OT-KB-006", "소재 부족·대체 승인 절차", "구매·생산", "소재, 재고, 부족, 대체"),
            "quote_process_flow.md": ("OT-KB-007", "원터치 CAD 견적 표준 흐름", "영업·견적", "견적, 접수, 도면, 승인"),
        }
        for filename, (document_id, title, owner, keywords) in metadata.items():
            path = self.docs_dir / filename
            if not path.is_file():
                continue
            connection.execute(
                "INSERT OR IGNORE INTO knowledge_documents VALUES (?,?,?,?,?,?,?,?,?,?)",
                (document_id, title, filename, "R0", owner, "2026-09-04", "샘플·미승인",
                 keywords, path.read_text(encoding="utf-8"), "원터치 로컬 지식문서"),
            )
        rules = [
            ("OT-RULE-001", "낮은 도면 신뢰도", "drawings", "overall_confidence < 0.80", "설계·견적", "원본 도면과 재질·두께를 확인하고 수작업 견적으로 전환", "OT-KB-001", "R0", "샘플·미승인"),
            ("OT-RULE-002", "소재 안전재고 부족", "material_inventory", "available_kg - reserved_kg < safety_stock_kg", "구매·생산", "영향 견적을 확인하고 구매 또는 대체 승인 요청", "OT-KB-006", "R0", "샘플·미승인"),
            ("OT-RULE-003", "도면 개정 미확인", "drawings", "revision = '미확인'", "설계", "최신 도면 버전 확인 전 견적 확정 금지", "OT-KB-005", "R0", "샘플·미승인"),
            ("OT-RULE-004", "중간 신뢰도 담당자 검토", "cost_estimates", "confidence >= 0.80 AND confidence < 0.95", "견적", "도면 예외와 원가 근거 확인 후 승인", "OT-KB-003", "R0", "샘플·미승인"),
            ("OT-RULE-005", "자동 산출 후보 최종승인", "cost_estimates", "confidence >= 0.95", "영업·견적 책임자", "고객 발송 전 최종 승인", "OT-KB-003", "R0", "샘플·미승인"),
        ]
        connection.executemany("INSERT OR IGNORE INTO rules VALUES (?,?,?,?,?,?,?,?,?)", rules)

    def _query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._connect() as connection:
            return self._dicts(connection.execute(sql, params).fetchall())

    def dashboard(self, date: str = DEMO_DATE) -> dict[str, Any]:
        quotes = self.quote_requests(None)
        estimates = self.cost_estimate(None)
        return {
            "new_quotes": len([row for row in quotes if row["received_at"].startswith(date)]),
            "drawing_reviews": len([row for row in self.drawing_features(None) if row["parse_status"] != "추출완료"]),
            "approval_pending": len(self.approval_queue(None, True)),
            "manual_routes": len([row for row in estimates if float(row["confidence"]) < 0.80]),
            "average_confidence": round(sum(float(row["confidence"]) for row in estimates) / len(estimates) * 100, 1),
            "material_risks": len(self.material_availability(True)),
            "provenance": "demo_data",
        }

    def quote_requests(self, quote_id: str | None) -> list[dict[str, Any]]:
        if quote_id is None:
            return self._query("SELECT * FROM quote_requests ORDER BY due_at")
        return self._query("SELECT * FROM quote_requests WHERE quote_id=? ORDER BY due_at", (quote_id,))

    def drawing_features(self, drawing_id: str | None) -> list[dict[str, Any]]:
        sql = "SELECT d.*, f.length_mm, f.width_mm, f.height_mm, f.thickness_mm, f.material, f.round_holes, f.slots, f.hole_spacing_mm, f.feature_confidence, f.provenance FROM drawings d JOIN manufacturing_features f USING(drawing_id)"
        if drawing_id is None:
            return self._query(sql)
        return self._query(sql + " WHERE d.drawing_id=?", (drawing_id,))

    def bom(self, quote_id: str) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM bom_items WHERE quote_id=? ORDER BY bom_id", (quote_id,))

    def routing(self, quote_id: str) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM routings WHERE quote_id=? ORDER BY sequence_no", (quote_id,))

    def cost_estimate(self, quote_id: str | None) -> list[dict[str, Any]]:
        if quote_id is None:
            return self._query("SELECT * FROM cost_estimates ORDER BY calculated_at DESC")
        return self._query("SELECT * FROM cost_estimates WHERE quote_id=? ORDER BY calculated_at DESC", (quote_id,))

    def similar_quotes(self, product_family: str | None) -> list[dict[str, Any]]:
        sql = "SELECT *, ROUND((quoted_total_krw-actual_cost_krw)/actual_cost_krw*100,2) AS quote_variance_pct FROM quote_history"
        if product_family is None:
            return self._query(sql + " ORDER BY completed_at DESC")
        return self._query(sql + " WHERE product_family=? ORDER BY completed_at DESC", (product_family,))

    def material_availability(self, risks_only: bool = False) -> list[dict[str, Any]]:
        return self._query("SELECT *, available_kg-reserved_kg AS free_kg, CASE WHEN available_kg-reserved_kg<safety_stock_kg THEN '부족' ELSE '정상' END AS status FROM material_inventory WHERE (?=0 OR available_kg-reserved_kg<safety_stock_kg) ORDER BY material_code", (int(risks_only),))

    def approval_queue(self, quote_id: str | None, pending_only: bool = False) -> list[dict[str, Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if quote_id is not None:
            conditions.append("quote_id=?"); params.append(quote_id)
        if pending_only:
            conditions.append("approval_status!='승인완료'")
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return self._query("SELECT * FROM approval_queue" + where + " ORDER BY requested_at", tuple(params))

    def order_feedback(self, quote_id: str | None) -> list[dict[str, Any]]:
        if quote_id is None:
            return self._query("SELECT * FROM order_feedback ORDER BY updated_at DESC")
        return self._query("SELECT * FROM order_feedback WHERE quote_id=? ORDER BY updated_at DESC", (quote_id,))

    def quote_snapshot(self, quote_id: str) -> dict[str, Any]:
        quote = self.quote_requests(quote_id)
        if not quote:
            return {}
        drawing_id = quote[0]["drawing_id"]
        materials = self.material_availability(False)
        bom_specs = {row["specification"] for row in self.bom(quote_id)}
        return {"quote": quote[0], "drawing": self.drawing_features(drawing_id)[0],
                "bom": self.bom(quote_id), "routing": self.routing(quote_id),
                "estimate": self.cost_estimate(quote_id)[0], "approvals": self.approval_queue(quote_id, True),
                "materials": [row for row in materials if row["specification"] in bom_specs]}

    def rules(self, source_table: str | None = None) -> list[dict[str, Any]]:
        if source_table is None:
            return self._query("SELECT * FROM rules ORDER BY rule_id")
        return self._query("SELECT * FROM rules WHERE source_table=? ORDER BY rule_id", (source_table,))

    def knowledge_documents(self) -> list[dict[str, Any]]:
        return self._query(
            "SELECT document_id,title,filename,revision,owner,effective_date,status,keywords,source_label "
            "FROM knowledge_documents ORDER BY document_id"
        )

    @staticmethod
    def _search_terms(query: str) -> set[str]:
        tokens = [token.lower() for token in re.findall(r"[가-힣A-Za-z0-9]+", query)]
        terms = {token for token in tokens if len(token) >= 2}
        for token in tokens:
            terms.update(token[index:index + 2] for index in range(len(token) - 1))
        return terms

    def search_knowledge(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        terms = self._search_terms(query)
        rows = self._query("SELECT * FROM knowledge_documents ORDER BY document_id")
        scored: list[tuple[int, dict[str, Any]]] = []
        for row in rows:
            haystack = " ".join(str(row.get(key, "")) for key in ("title", "filename", "keywords", "body")).lower()
            score = sum(3 if term in str(row.get("keywords", "")).lower() else 1 for term in terms if term in haystack)
            if score:
                item = dict(row)
                item["score"] = score
                item["text"] = item.pop("body")[:900]
                scored.append((score, item))
        return [item for _, item in sorted(scored, key=lambda pair: (-pair[0], pair[1]["document_id"]))[:max(1, min(limit, 10))]]

    TABLE_LABELS = {
        "quote_requests": "견적 요청", "drawings": "도면", "manufacturing_features": "제조 Feature",
        "bom_items": "BOM", "routings": "공정 Routing", "cost_estimates": "원가 견적",
        "quote_history": "유사 견적", "material_inventory": "소재 재고", "approval_queue": "승인 대기",
        "order_feedback": "생산원가 피드백", "knowledge_documents": "지식문서", "rules": "판정 규칙",
    }

    def table_catalog(self) -> list[dict[str, Any]]:
        return [{"table": table, "label": label, "rows": self._query(f"SELECT COUNT(*) AS count FROM {table}")[0]["count"]}
                for table, label in self.TABLE_LABELS.items()]

    def browse_table(self, table: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if table not in self.TABLE_LABELS:
            raise ValueError(f"조회가 허용되지 않은 테이블: {table}")
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))
        return self._query(f"SELECT * FROM {table} ORDER BY rowid LIMIT ? OFFSET ?", (safe_limit, safe_offset))

    def get_setting(self, key: str) -> str | None:
        rows = self._query("SELECT setting_value FROM settings WHERE setting_key=?", (key,))
        return str(rows[0]["setting_value"]) if rows else None

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value))
