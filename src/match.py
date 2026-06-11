import pandas as pd

from src.db import get_connection
from src.normalize import normalize_account_name


def rebuild_matches() -> int:
    conn = get_connection()

    df = pd.read_sql_query("SELECT * FROM raw_accounts", conn)

    cur = conn.cursor()
    cur.execute("DELETE FROM account_matches")

    count = 0

    df["normalized_name"] = df["name"].apply(normalize_account_name)

    ad_accounts = df[df["source"] == "AD"]
    entra_accounts = df[df["source"] == "ENTRA"]
    silverfort_accounts = df[df["source"] == "SILVERFORT"]

    # AD ↔ Entra basic name match
    for _, ad in ad_accounts.iterrows():
        ad_name = ad["normalized_name"]
        if not ad_name:
            continue

        candidates = entra_accounts[entra_accounts["normalized_name"] == ad_name]

        for _, entra in candidates.iterrows():
            cur.execute(
                """
                INSERT INTO account_matches (
                    left_source,
                    left_object_id,
                    right_source,
                    right_object_id,
                    confidence,
                    reason
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ad["source"],
                    ad["source_object_id"],
                    entra["source"],
                    entra["source_object_id"],
                    0.80,
                    "same_normalized_name",
                ),
            )
            count += 1

    # AD ↔ Silverfort basic name match
    for _, ad in ad_accounts.iterrows():
        ad_name = ad["normalized_name"]
        if not ad_name:
            continue

        candidates = silverfort_accounts[silverfort_accounts["normalized_name"] == ad_name]

        for _, sf in candidates.iterrows():
            cur.execute(
                """
                INSERT INTO account_matches (
                    left_source,
                    left_object_id,
                    right_source,
                    right_object_id,
                    confidence,
                    reason
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ad["source"],
                    ad["source_object_id"],
                    sf["source"],
                    sf["source_object_id"],
                    0.85,
                    "same_normalized_name",
                ),
            )
            count += 1

    conn.commit()
    conn.close()

    return count