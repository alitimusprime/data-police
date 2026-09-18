import duckdb
import polars as pl


def transform(asset_id, frames, paths, scenario=None):
    match asset_id:
        case "clean_orders":
            return (
                frames["raw_orders"].unique().with_columns(pl.col("customer_id").cast(pl.Int64, strict=False))
            )
        case "clean_payments":
            frame = frames["raw_payments"]
            if "payment_method" not in frame.columns:
                raise ValueError("payment_method is missing from the payment contract")
            return frame.with_columns(pl.col("amount").cast(pl.Float64))
        case "clean_inventory":
            return frames["raw_inventory"].with_columns(pl.col("quantity").cast(pl.Int64))
        case "fact_orders":
            payments = frames["clean_payments"].rename({"amount": "captured_amount"})
            result = (
                frames["clean_orders"]
                .join(payments, on="order_id", how="left")
                .join(frames["dim_countries"], on="country_code", how="left")
            )
            if scenario == "bad_transform":
                result = result.with_columns((pl.col("captured_amount") * 2).alias("captured_amount"))
            return result.with_columns(
                (pl.col("captured_amount") - pl.col("amount")).alias("reconciliation_delta")
            )
        case "fact_shipments":
            return frames["raw_shipments"].join(
                frames["clean_orders"].select("order_id", "customer_id"), on="order_id", how="left"
            )
        case "fact_order_lines":
            return (
                frames["raw_order_items"]
                .join(frames["dim_products"], on="product_id", how="left")
                .with_columns((pl.col("quantity") * pl.col("unit_price")).alias("line_revenue"))
            )
        case "country_revenue":
            # DuckDB reads the committed Parquet boundary, not an unrelated example query.
            with duckdb.connect() as conn:
                result = conn.execute(
                    "SELECT coalesce(country_name, 'Unmatched') AS country_name, count(*) AS orders, round(sum(captured_amount),2) AS revenue FROM read_parquet(?) GROUP BY 1 ORDER BY 1",
                    [str(paths["fact_orders"])],
                )
                names = [c[0] for c in result.description]
                return pl.DataFrame(result.fetchall(), schema=names, orient="row")
        case "daily_revenue":
            frame = frames["fact_orders"]
            return (
                frame.with_columns(pl.col("ordered_at").str.slice(0, 10).alias("date"))
                .group_by("date")
                .agg(pl.col("captured_amount").sum().round(2).alias("revenue"), pl.len().alias("orders"))
            )
        case "payment_methods":
            return (
                frames["clean_payments"]
                .group_by("payment_method")
                .agg(pl.len().alias("payments"), pl.col("amount").sum().round(2).alias("revenue"))
            )
        case "inventory_health":
            return (
                frames["clean_inventory"]
                .join(frames["dim_products"], on="product_id", how="left")
                .with_columns((pl.col("quantity") < 20).alias("low_stock"))
            )
        case "product_revenue":
            return (
                frames["fact_order_lines"]
                .group_by("category")
                .agg(pl.col("line_revenue").sum().round(2).alias("revenue"), pl.len().alias("lines"))
            )
        case _:
            raise ValueError(f"No transformation is registered for {asset_id}")
