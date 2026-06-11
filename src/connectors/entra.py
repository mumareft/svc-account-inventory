import os
import httpx
from dotenv import load_dotenv
from azure.identity import ClientSecretCredential

from src.models import RawAccount

load_dotenv()

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"


def get_graph_token() -> str:
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )

    token = credential.get_token(GRAPH_SCOPE)
    return token.token


def fetch_entra_service_principals() -> list[RawAccount]:
    token = get_graph_token()

    headers = {
        "Authorization": f"Bearer {token}",
    }

    url = (
        "https://graph.microsoft.com/v1.0/servicePrincipals"
        "?$select=id,appId,displayName,accountEnabled,servicePrincipalType,tags"
        #SID_, SVC,
    )

    accounts: list[RawAccount] = []

    with httpx.Client(timeout=60) as client:
        while url:
            response = client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()

            for item in data.get("value", []):
                accounts.append(
                    RawAccount(
                        source="ENTRA",
                        source_object_id=item["id"],
                        name=item.get("displayName"),
                        display_name=item.get("displayName"),
                        enabled=item.get("accountEnabled"),
                        account_type=item.get("servicePrincipalType") or "service_principal",
                        last_seen=None,
                        raw=item,
                    )
                )

            url = data.get("@odata.nextLink")

    return accounts