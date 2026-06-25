"""
POS Transaction Correlation.

Loads pos_transactions.csv and correlates with visitor sessions.
A visitor who was in BILLING zone within 5 minutes before a transaction
timestamp counts as a confirmed purchase.

Also provides basket value analytics.
"""

import os
import csv
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct

from app.database import EventRecord

POS_CSV_PATH = os.getenv("POS_CSV_PATH", "data/pos_transactions.csv")
CORRELATION_WINDOW_MINUTES = 5


def load_pos_transactions(store_id: str) -> List[Dict]:
    """Load POS transactions for a given store from CSV.

    Supports two formats:
      1. Normalised: store_id, transaction_id, timestamp, basket_value_inr
      2. Raw Purplle: order_id, order_date, order_time, store_id, GMV, NMV, ...
    """
    transactions = []
    if not os.path.exists(POS_CSV_PATH):
        return transactions
    try:
        with open(POS_CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            # Detect format by checking column names
            is_normalised = "basket_value_inr" in fieldnames

            for row in reader:
                sid = row.get("store_id", "").strip()
                # Accept exact match OR legacy ST1008 mapping
                if sid not in (store_id, "ST1008"):
                    continue
                try:
                    if is_normalised:
                        # Format 1: normalised CSV with ISO timestamp
                        ts_str = row.get("timestamp", "").strip()
                        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        gmv = float(row.get("basket_value_inr", 0) or 0)
                        order_id = row.get("transaction_id", "").strip()
                        transactions.append({
                            "order_id": order_id,
                            "timestamp": dt,
                            "gmv": gmv,
                            "nmv": gmv * 0.85,  # estimate NMV at 85% of GMV
                            "invoice": order_id,
                        })
                    else:
                        # Format 2: raw Purplle CSV with separate date/time columns
                        date_str = row.get("order_date", "").strip()
                        time_str = row.get("order_time", "").strip()
                        if date_str and time_str:
                            dt = datetime.strptime(
                                f"{date_str} {time_str}", "%d-%m-%Y %H:%M:%S"
                            ).replace(tzinfo=timezone.utc)
                        else:
                            continue
                        gmv = float(row.get("GMV", 0) or row.get("total_amount", 0) or 0)
                        nmv = float(row.get("NMV", 0) or gmv * 0.85)
                        order_id = row.get("order_id", "").strip()
                        transactions.append({
                            "order_id": order_id,
                            "timestamp": dt,
                            "gmv": gmv,
                            "nmv": nmv,
                            "invoice": row.get("invoice_number", order_id),
                        })
                except Exception:
                    continue
    except Exception:
        pass
    return transactions


def get_confirmed_purchases(store_id: str, db: Session, date_str: Optional[str] = None) -> Dict:
    """
    Correlate billing zone visitors with POS transactions.
    Returns confirmed purchase count and revenue metrics.
    """
    from app.metrics import get_today_window
    if date_str:
        try:
            day = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            start_ts = day.strftime("%Y-%m-%dT00:00:00Z")
            end_ts = day.strftime("%Y-%m-%dT23:59:59Z")
        except Exception:
            start_ts, end_ts = get_today_window()
    else:
        start_ts, end_ts = get_today_window()

    transactions = load_pos_transactions(store_id)

    # Filter transactions to the date window; fall back to all data for demos/replays
    window_txns = [
        t for t in transactions
        if start_ts <= t["timestamp"].strftime("%Y-%m-%dT%H:%M:%SZ") <= end_ts
    ]
    if not window_txns:
        window_txns = transactions

    # Get visitors who were in BILLING zone
    billing_events = (
        db.query(EventRecord)
        .filter(
            EventRecord.store_id == store_id,
            EventRecord.is_staff == False,
            EventRecord.event_type.in_(["ZONE_ENTER", "BILLING_QUEUE_JOIN"]),
            EventRecord.zone_id == "BILLING",
            EventRecord.timestamp >= start_ts,
        )
        .all()
    )

    # For each transaction, find visitors in billing within 5-min window
    confirmed_visitors = set()
    matched_txns = []

    for txn in window_txns:
        txn_ts = txn["timestamp"]
        window_start = (txn_ts - timedelta(minutes=CORRELATION_WINDOW_MINUTES)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        window_end = txn_ts.strftime("%Y-%m-%dT%H:%M:%SZ")

        for ev in billing_events:
            if window_start <= ev.timestamp <= window_end:
                confirmed_visitors.add(ev.visitor_id)
                matched_txns.append(txn)
                break

    # Revenue metrics from POS CSV
    total_gmv = sum(t["gmv"] for t in window_txns)
    total_nmv = sum(t["nmv"] for t in window_txns)
    total_orders = len(set(t["order_id"] for t in window_txns))
    avg_basket = total_gmv / total_orders if total_orders > 0 else 0.0

    return {
        "confirmed_purchases": len(confirmed_visitors),
        "total_transactions": total_orders,
        "total_gmv_inr": round(total_gmv, 2),
        "total_nmv_inr": round(total_nmv, 2),
        "avg_basket_value_inr": round(avg_basket, 2),
        "correlation_window_minutes": CORRELATION_WINDOW_MINUTES,
    }


def _raw_pos_rows(store_id: str) -> List[Dict]:
    """Return raw CSV rows for a store — used by department breakdown endpoint."""
    rows = []
    if not os.path.exists(POS_CSV_PATH):
        return rows
    try:
        with open(POS_CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sid = row.get("store_id", "").strip()
                if sid == store_id or sid == "ST1008":
                    rows.append(dict(row))
    except Exception:
        pass
    return rows
