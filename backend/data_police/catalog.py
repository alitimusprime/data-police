from dataclasses import dataclass

from sqlalchemy import select

from .config import settings
from .models import Dataset, Lease, LineageEdge, Rule, RuleVersion, WorkspaceState


@dataclass(frozen=True)
class Asset:
    id: str
    layer: str
    source: str
    parents: tuple[str, ...] = ()
    description: str = ""
    owner: str = "Data Platform"
    critical: bool = False


# The execution engine and lineage registry share this contract. There is no separate UI graph.
ASSETS = [
    Asset(
        "raw_orders",
        "raw",
        "PostgreSQL",
        description="Immutable order batches extracted from the retail database.",
    ),
    Asset("raw_order_items", "raw", "PostgreSQL", description="Order line quantities and prices."),
    Asset("raw_payments", "raw", "REST API", description="Paginated responses from the payment provider."),
    Asset("raw_shipments", "raw", "REST API", description="Shipment statuses from the fulfillment provider."),
    Asset(
        "raw_inventory", "raw", "CSV", description="Checksummed inventory snapshots from the supplier feed."
    ),
    Asset(
        "dim_countries",
        "reference",
        "PostgreSQL",
        description="Accepted country keys and readable country names.",
    ),
    Asset("dim_customers", "reference", "PostgreSQL", description="Synthetic customer directory."),
    Asset("dim_products", "reference", "PostgreSQL", description="Retail product catalog."),
    Asset(
        "clean_orders",
        "staging",
        "Transformation",
        ("raw_orders",),
        "Typed orders with exact duplicate rows removed.",
    ),
    Asset(
        "clean_payments",
        "staging",
        "Transformation",
        ("raw_payments",),
        "Typed payments, preserving unexpected country codes for investigation.",
    ),
    Asset(
        "clean_inventory",
        "staging",
        "Transformation",
        ("raw_inventory",),
        "Typed stock quantities and supplier metadata.",
    ),
    Asset(
        "fact_orders",
        "curated",
        "Transformation",
        ("clean_orders", "clean_payments", "dim_countries", "dim_customers"),
        "Order-payment joins with country resolution and join-quality flags.",
        "Analytics Engineering",
        True,
    ),
    Asset(
        "fact_shipments",
        "curated",
        "Transformation",
        ("raw_shipments", "clean_orders"),
        "Shipments linked to their orders.",
        "Operations",
    ),
    Asset(
        "fact_order_lines",
        "curated",
        "Transformation",
        ("raw_order_items", "dim_products"),
        "Order lines enriched with product categories.",
        "Analytics Engineering",
    ),
    Asset(
        "country_revenue",
        "analytics",
        "Transformation",
        ("fact_orders",),
        "Captured revenue grouped by resolved country, with unmatched revenue kept separately.",
        "Finance",
        True,
    ),
    Asset(
        "daily_revenue",
        "analytics",
        "Transformation",
        ("fact_orders",),
        "Daily captured revenue totals, including unmatched countries.",
        "Finance",
        True,
    ),
    Asset(
        "payment_methods",
        "analytics",
        "Transformation",
        ("clean_payments",),
        "Payment-method mix and captured value.",
        "Finance",
    ),
    Asset(
        "inventory_health",
        "analytics",
        "Transformation",
        ("clean_inventory", "dim_products"),
        "Product inventory and low-stock indicators.",
        "Operations",
    ),
    Asset(
        "product_revenue",
        "analytics",
        "Transformation",
        ("fact_order_lines",),
        "Sales value by product category.",
        "Analytics Engineering",
    ),
]
ASSET_MAP = {a.id: a for a in ASSETS}

SCENARIOS = [
    {
        "id": "country_code",
        "name": "Country code change",
        "category": "Data contract",
        "description": "The payment source begins sending PAK instead of PK. Track the broken country join and downstream reporting impact.",
        "target": "raw_payments",
    },
    {
        "id": "null_spike",
        "name": "Missing customer identifiers",
        "category": "Completeness",
        "description": "Forty percent of incoming orders lose their customer identifier.",
        "target": "raw_orders",
    },
    {
        "id": "duplicates",
        "name": "Duplicate order delivery",
        "category": "Uniqueness",
        "description": "The source resends 25% of orders within the same extraction batch.",
        "target": "raw_orders",
    },
    {
        "id": "missing_records",
        "name": "Partial API response",
        "category": "Volume",
        "description": "The provider returns only 40% of payments with a successful HTTP response.",
        "target": "raw_payments",
    },
    {
        "id": "stale",
        "name": "Paused ingestion",
        "category": "Freshness",
        "description": "Stop materializations while the independent freshness monitor continues. Default threshold: 180 seconds.",
        "target": "raw_orders",
    },
    {
        "id": "distribution",
        "name": "Payment mix shift",
        "category": "Distribution",
        "description": "Cash on delivery replaces the usual card and wallet mix.",
        "target": "raw_payments",
    },
    {
        "id": "invalid_values",
        "name": "Negative payment amounts",
        "category": "Validity",
        "description": "One in four payments contains a negative captured amount.",
        "target": "raw_payments",
    },
    {
        "id": "schema_removed",
        "name": "Removed API field",
        "category": "Schema",
        "description": "The provider removes the payment_method field from its actual response.",
        "target": "raw_payments",
    },
    {
        "id": "bad_transform",
        "name": "Revenue calculation regression",
        "category": "Transformation",
        "description": "A faulty fact-order transformation doubles captured amounts. A reconciliation check finds the mismatch.",
        "target": "fact_orders",
    },
    {
        "id": "api_failure",
        "name": "Provider unavailable",
        "category": "Availability",
        "description": "The live payment endpoint returns HTTP 503; extraction retries before recording a pipeline failure.",
        "target": "raw_payments",
    },
]


def initialize_catalog(session):
    if session.scalar(select(Dataset.id).limit(1)):
        return
    for asset in ASSETS:
        session.add(
            Dataset(
                id=asset.id,
                name=asset.id,
                layer=asset.layer,
                source="SQLite"
                if asset.source == "PostgreSQL" and settings.source_database_url.startswith("sqlite")
                else asset.source,
                description=asset.description,
                owner=asset.owner,
                critical=asset.critical,
            )
        )
    session.flush()
    for asset in ASSETS:
        for parent in asset.parents:
            session.add(
                LineageEdge(source_id=parent, target_id=asset.id, transformation=asset.id, version="1")
            )
    definitions = [
        ("raw_orders", "Order IDs are unique", "unique", "order_id", {}, "critical"),
        ("raw_orders", "Customer identifier is present", "not_null", "customer_id", {}, "critical"),
        ("raw_orders", "Order amount is nonnegative", "range", "amount", {"min": 0}, "critical"),
        (
            "raw_orders",
            "Valid order status",
            "accepted",
            "status",
            {"values": ["paid", "processing", "cancelled"]},
            "warning",
        ),
        (
            "raw_payments",
            "Payment country matches contract",
            "accepted",
            "country_code",
            {"values": ["PK", "US", "GB", "AE", "DE"]},
            "critical",
        ),
        ("raw_payments", "Captured amount is nonnegative", "range", "amount", {"min": 0}, "critical"),
        (
            "raw_payments",
            "Payment schema is complete",
            "schema",
            None,
            {"columns": ["payment_id", "order_id", "amount", "country_code", "payment_method"]},
            "critical",
        ),
        (
            "raw_payments",
            "Payment methods are accepted",
            "accepted",
            "payment_method",
            {"values": ["card", "wallet", "cod"]},
            "warning",
        ),
        ("fact_orders", "Country join resolves", "not_null", "country_name", {}, "critical"),
        ("fact_orders", "Every order has a payment", "not_null", "payment_id", {}, "critical"),
        (
            "fact_orders",
            "Customer reference exists",
            "reference",
            "customer_id",
            {"dataset": "dim_customers", "column": "customer_id"},
            "critical",
        ),
        (
            "fact_orders",
            "Captured amount reconciles",
            "range",
            "reconciliation_delta",
            {"min": -0.01, "max": 0.01},
            "critical",
        ),
        ("raw_inventory", "Stock quantities are valid", "range", "quantity", {"min": 0}, "warning"),
        (
            "dim_customers",
            "Email syntax is valid",
            "pattern",
            "email",
            {"pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"},
            "warning",
        ),
    ]
    for dataset, name, kind, col, params, severity in definitions:
        rule = Rule(dataset_id=dataset, name=name, kind=kind, column=col, params=params, severity=severity)
        session.add(rule)
        session.flush()
        session.add(
            RuleVersion(
                rule_id=rule.id,
                version=1,
                definition={
                    "kind": kind,
                    "column": col,
                    "params": params,
                    "name": name,
                    "severity": severity,
                    "enabled": True,
                },
            )
        )
    session.add(WorkspaceState(key="simulator", value={"scenario": None}))
    session.add(WorkspaceState(key="sequence", value={"number": 0}))
    session.add(Lease(key="pipeline", owner="", expires_at=""))
