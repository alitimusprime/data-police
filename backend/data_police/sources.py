"""Seeded business generator and real SQL, HTTP and CSV extraction boundaries."""

import csv
import hashlib
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import polars as pl
from sqlalchemy import Column, Float, Integer, MetaData, String, Table, delete, insert, select

from .config import settings
from .db import make_engine


source_metadata = MetaData()
ENTITY_FIELDS = {
    "orders": {
        "order_id": Integer,
        "customer_id": Integer,
        "amount": Float,
        "status": String(30),
        "ordered_at": String(40),
    },
    "order_items": {
        "line_id": Integer,
        "order_id": Integer,
        "product_id": Integer,
        "quantity": Integer,
        "unit_price": Float,
    },
    "payments": {
        "payment_id": Integer,
        "order_id": Integer,
        "amount": Float,
        "country_code": String(8),
        "payment_method": String(30),
        "captured_at": String(40),
    },
    "shipments": {
        "shipment_id": Integer,
        "order_id": Integer,
        "status": String(30),
        "days_in_transit": Integer,
    },
    "countries": {"country_code": String(8), "country_name": String(100)},
    "customers": {"customer_id": Integer, "email": String(180), "segment": String(30)},
    "products": {"product_id": Integer, "product_name": String(100), "category": String(60)},
}
SOURCE_TABLES = {
    name: Table(
        "source_" + name,
        source_metadata,
        Column("batch_id", String(40), primary_key=True),
        Column("row_number", Integer, primary_key=True),
        *[Column(field, type_) for field, type_ in fields.items()],
    )
    for name, fields in ENTITY_FIELDS.items()
}
source_state = Table(
    "provider_state",
    source_metadata,
    Column("key", String(40), primary_key=True),
    Column("value", String(80)),
)


def source_engine():
    return make_engine(settings.source_database_url)


def generate_batch(batch_id: str, sequence: int, scenario: str | None):
    rng = random.Random(7100 + sequence)
    count = rng.randint(320, 350)
    timestamp = datetime.now(timezone.utc).isoformat()
    countries = [
        {"country_code": code, "country_name": name}
        for code, name in [
            ("PK", "Pakistan"),
            ("US", "United States"),
            ("GB", "United Kingdom"),
            ("AE", "UAE"),
            ("DE", "Germany"),
        ]
    ]
    customers = [
        {"customer_id": i, "email": f"customer{i}@example.test", "segment": ["consumer", "business"][i % 2]}
        for i in range(1, 101)
    ]
    products = [
        {
            "product_id": i,
            "product_name": f"Retail item {i:02}",
            "category": ["Electronics", "Home", "Clothing", "Outdoors"][i % 4],
        }
        for i in range(1, 41)
    ]
    orders, payments, shipments, items = [], [], [], []
    # Keep healthy regional traffic within a bounded envelope. Fault scenarios, not
    # uncontrolled fixture noise, should drive the reproducible demonstration.
    country_codes = [
        code
        for code, weight in [("PK", 30), ("US", 30), ("GB", 18), ("AE", 12), ("DE", 10)]
        for _ in range(round(count * weight / 100))
    ]
    country_codes += ["US"] * max(0, count - len(country_codes))
    rng.shuffle(country_codes)
    for i in range(count):
        order_id = sequence * 10000 + i + 1
        amount = round(rng.uniform(30, 220), 2)
        code = country_codes[i]
        customer = rng.randint(1, 100)
        orders.append(
            {
                "order_id": order_id,
                "customer_id": None if scenario == "null_spike" and i % 5 < 2 else customer,
                "amount": amount,
                "status": "paid",
                "ordered_at": timestamp,
            }
        )
        payment = {
            "payment_id": order_id + 1000000,
            "order_id": order_id,
            "amount": -amount if scenario == "invalid_values" and i % 4 == 0 else amount,
            "country_code": "PAK" if scenario == "country_code" and code == "PK" else code,
            "payment_method": rng.choices(
                ["card", "wallet", "cod"], [8, 5, 87] if scenario == "distribution" else [60, 25, 15]
            )[0],
            "captured_at": timestamp,
        }
        if scenario == "schema_removed":
            payment.pop("payment_method")
        payments.append(payment)
        shipments.append(
            {
                "shipment_id": order_id,
                "order_id": order_id,
                "status": rng.choice(["delivered", "in_transit", "processing"]),
                "days_in_transit": rng.randint(0, 5),
            }
        )
        items.append(
            {
                "line_id": order_id,
                "order_id": order_id,
                "product_id": rng.randint(1, 40),
                "quantity": 1,
                "unit_price": amount,
            }
        )
    if scenario == "duplicates":
        orders.extend(dict(r) for r in orders[: count // 4])
    if scenario == "missing_records":
        payments = payments[: int(count * 0.4)]
    entities = {
        "orders": orders,
        "order_items": items,
        "payments": payments,
        "shipments": shipments,
        "countries": countries,
        "customers": customers,
        "products": products,
    }
    engine = source_engine()
    source_metadata.create_all(engine)
    with engine.begin() as conn:
        # Idempotent generation of one explicit batch, never destructive to other batches.
        conn.execute(delete(source_state).where(source_state.c.key == "scenario"))
        conn.execute(insert(source_state), {"key": "scenario", "value": scenario or "healthy"})
        for entity, rows in entities.items():
            table = SOURCE_TABLES[entity]
            conn.execute(delete(table).where(table.c.batch_id == batch_id))
            conn.execute(
                insert(table),
                [{"batch_id": batch_id, "row_number": idx, **row} for idx, row in enumerate(rows)],
            )
    engine.dispose()
    folder = settings.data_dir / "feeds"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"inventory_{batch_id}.csv"
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["product_id", "quantity", "supplier", "updated_at"])
        writer.writeheader()
        for product in products:
            writer.writerow(
                {
                    "product_id": product["product_id"],
                    "quantity": rng.randint(10, 200),
                    "supplier": "Northstar Supply",
                    "updated_at": timestamp,
                }
            )
    return path


class SQLConnector:
    """Keyset-paginated, immutable batch extraction from native relational source tables."""

    def __init__(self, url=None):
        self.engine = make_engine(url or settings.source_database_url)

    def test(self):
        with self.engine.connect() as conn:
            conn.execute(select(1))
        return {"ok": True}

    def extract(self, entity, batch_id):
        rows, cursor = [], -1
        table = SOURCE_TABLES[entity]
        with self.engine.connect() as conn:
            while True:
                result = (
                    conn.execute(
                        select(table)
                        .where(table.c.batch_id == batch_id, table.c.row_number > cursor)
                        .order_by(table.c.row_number)
                        .limit(250)
                    )
                    .mappings()
                    .all()
                )
                if not result:
                    break
                rows.extend({key: row[key] for key in ENTITY_FIELDS[entity]} for row in result)
                cursor = result[-1]["row_number"]
        return pl.DataFrame(rows, infer_schema_length=None)

    def close(self):
        self.engine.dispose()


class RESTConnector:
    def __init__(self, base_url=None):
        self.base_url = (base_url or settings.demo_api_url).rstrip("/")

    def test(self):
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            client.get(self.base_url + "/health").raise_for_status()
        return {"ok": True}

    def extract(self, entity, batch_id):
        rows, offset = [], 0
        with httpx.Client(timeout=10, follow_redirects=False, trust_env=False) as client:
            for _ in range(1000):
                for attempt in range(3):
                    try:
                        response = client.get(
                            f"{self.base_url}/{entity}",
                            params={"batch_id": batch_id, "offset": offset, "limit": 100},
                        )
                        response.raise_for_status()
                        data = response.json()
                        break
                    except (httpx.TransportError, httpx.HTTPStatusError):
                        if attempt == 2:
                            raise RuntimeError(f"{entity} provider request failed after 3 attempts") from None
                        time.sleep(0.15 * 2**attempt)
                if not isinstance(data.get("items"), list):
                    raise ValueError("Provider response must contain an items array")
                rows.extend(data["items"])
                next_offset = data.get("next_offset")
                if next_offset is None:
                    return pl.DataFrame(rows, infer_schema_length=None)
                if not isinstance(next_offset, int) or next_offset <= offset:
                    raise ValueError("Provider pagination cursor did not advance")
                offset = next_offset
        raise ValueError("Provider pagination exceeded the bounded extraction limit")


class CSVConnector:
    def extract(self, path: Path):
        resolved = path.resolve()
        if not resolved.is_relative_to((settings.data_dir / "feeds").resolve()):
            raise ValueError("Feed must be inside the configured feed directory")
        if resolved.stat().st_size > 20_000_000:
            raise ValueError("CSV exceeds the local ingestion size limit")
        frame = pl.read_csv(resolved, infer_schema_length=None)
        if not {"product_id", "quantity", "supplier", "updated_at"}.issubset(frame.columns):
            raise ValueError("Inventory feed is missing required columns")
        return frame, hashlib.sha256(resolved.read_bytes()).hexdigest()
