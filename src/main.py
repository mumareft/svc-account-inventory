import json
import typer
import pandas as pd
from rich import print
from pathlib import Path
from src.db import init_db
from src.db import get_connection, init_db
from src.models import RawAccount
from src.normalize import normalize_account_name
import shutil

app = typer.Typer()
DB_PATH = Path("data/inventory.db")
EXPORTS_PATH = Path("data/exports")

@app.command()
def init():
    init_db()
    print("[green]Initialized local inventory database.[/green]")


@app.command()
def reset_db(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation.",
    )
):
    """
    Delete the local inventory database and recreate it empty.
    """

    if not yes:
        confirmed = typer.confirm(
            "This will delete data/inventory.db and all stored inventory data. Continue?"
        )

        if not confirmed:
            print("[yellow]Reset cancelled.[/yellow]")
            raise typer.Exit()

    if DB_PATH.exists():
        DB_PATH.unlink()
        print("[green]Deleted existing inventory database.[/green]")
    else:
        print("[yellow]No existing inventory database found.[/yellow]")

    init_db()

    print("[green]Created a fresh empty inventory database.[/green]")


@app.command()
def clean_exports(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation.",
    )
):
    """
    Delete generated export files.
    """

    if not yes:
        confirmed = typer.confirm(
            "This will delete all files inside data/exports. Continue?"
        )

        if not confirmed:
            print("[yellow]Clean cancelled.[/yellow]")
            raise typer.Exit()

    if EXPORTS_PATH.exists():
        shutil.rmtree(EXPORTS_PATH)
        print("[green]Deleted export files.[/green]")

    EXPORTS_PATH.mkdir(parents=True, exist_ok=True)
    print("[green]Created empty exports folder.[/green]")


def upsert_accounts(accounts: list[RawAccount]) -> None:
    conn = get_connection()
    cur = conn.cursor()

    for account in accounts:
        cur.execute(
            """
            INSERT INTO raw_accounts (
                source,
                source_object_id,
                name,
                display_name,
                enabled,
                account_type,
                last_seen,
                raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, source_object_id)
            DO UPDATE SET
                name = excluded.name,
                display_name = excluded.display_name,
                enabled = excluded.enabled,
                account_type = excluded.account_type,
                last_seen = excluded.last_seen,
                raw_json = excluded.raw_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                account.source,
                account.source_object_id,
                account.name,
                account.display_name,
                int(account.enabled) if account.enabled is not None else None,
                account.account_type,
                account.last_seen,
                json.dumps(account.raw),
            ),
        )

    conn.commit()
    conn.close()

@app.command()
def export_csv():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM raw_accounts", conn)
    conn.close()

    output_path = "data/exports/raw_accounts.csv"
    df.to_csv(output_path, index=False)

    print(f"[green]Exported {len(df)} accounts to {output_path}[/green]")

@app.command()
def sync_ad():
    print("Syncing Active Directory...")


@app.command()
def sync_entra():
    print("Syncing Entra...")


@app.command()
def sync_silverfort():
    print("Syncing Silverfort...")


@app.command()
def match():
    print("Matching accounts...")


@app.command()
def stats():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM raw_accounts", conn)
    conn.close()

    print("[bold]Accounts by source:[/bold]")
    print(df["source"].value_counts())

    print("\n[bold]Accounts by type:[/bold]")
    print(df["account_type"].value_counts(dropna=False))


@app.command()
def sync_fake():
    accounts = [
        RawAccount(
            source="AD",
            source_object_id="ad-001",
            name="svc-snow",
            display_name="ServiceNow Service Account",
            enabled=True,
            account_type="ad_user",
            last_seen=None,
            raw={"sAMAccountName": "svc-snow"},
        ),
        RawAccount(
            source="ENTRA",
            source_object_id="entra-001",
            name="svc-snow",
            display_name="ServiceNow App",
            enabled=True,
            account_type="service_principal",
            last_seen=None,
            raw={"appId": "fake-app-id"},
        ),
    ]

    upsert_accounts(accounts)
    print(f"[green]Synced {len(accounts)} fake accounts.[/green]")


@app.command()
def sync_ad():
    from src.connectors.ad import fetch_ad_service_accounts

    accounts = fetch_ad_service_accounts()
    upsert_accounts(accounts)

    print(f"[green]Synced {len(accounts)} AD accounts.[/green]")


@app.command()
def sync_entra():
    from src.connectors.entra import fetch_entra_app_identities

    accounts = fetch_entra_app_identities()
    upsert_accounts(accounts)

    print(f"[green]Synced {len(accounts)} Entra service principals.[/green]")


@app.command()
def sync_entra_users():
    from src.connectors.entra import fetch_entra_users_of_interest

    accounts = fetch_entra_users_of_interest()
    upsert_accounts(accounts)

    print(f"[green]Synced {len(accounts)} Entra users of interest.[/green]")


@app.command()
def match():
    from src.match import rebuild_matches

    count = rebuild_matches()
    print(f"[green]Created {count} matches.[/green]")


if __name__ == "__main__":
    app()