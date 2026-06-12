import os
import re
from datetime import datetime, timezone, timedelta
import httpx
from dotenv import load_dotenv
from azure.identity import ClientSecretCredential

from src.models import RawAccount

load_dotenv()

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"


SERVICE_ACCOUNT_PATTERNS = [
    r"(^|[^a-z0-9])sid[_\-.]",          # sid_, sid-, sid.
    r"(^|[^a-z0-9])svc([_\-.]|[a-z0-9])", # svc_, svc-, svc.prod, svcsql
    r"service",                         # service anywhere
    r"(^|[^a-z0-9])srv([_\-.]|[a-z0-9])",
    r"(^|[^a-z0-9])automation[_\-.]?",
    r"(^|[^a-z0-9])auto[_\-.]?",
    r"(^|[^a-z0-9])robot[_\-.]?",
    r"(^|[^a-z0-9])bot[_\-.]?",
]


def get_graph_token() -> str:
    credential = ClientSecretCredential(
        tenant_id=os.environ["AZURE_TENANT_ID"],
        client_id=os.environ["AZURE_CLIENT_ID"],
        client_secret=os.environ["AZURE_CLIENT_SECRET"],
    )
    return credential.get_token(GRAPH_SCOPE).token


def parse_graph_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    # Graph returns ISO 8601 UTC timestamps like: 2025-01-01T12:34:56Z
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_best_last_login(user: dict) -> tuple[str | None, str | None]:
    sign_in = user.get("signInActivity") or {}
    if sign_in.get("lastSuccessfulSignInDateTime"):
        return sign_in["lastSuccessfulSignInDateTime"], "lastSuccessfulSignInDateTime"
    if sign_in.get("lastSignInDateTime"):
        return sign_in["lastSignInDateTime"], "lastSignInDateTime"
    if sign_in.get("lastNonInteractiveSignInDateTime"):
        return sign_in["lastNonInteractiveSignInDateTime"], "lastNonInteractiveSignInDateTime"
    return None, None


def fetch_user_group_names(
    client: httpx.Client,
    headers: dict[str, str],
    user_id: str,
    transitive: bool = False,
) -> list[str]:
    """
    Fetch group display names for a user.

    transitive=False -> direct groups only
    transitive=True  -> direct + nested groups
    """

    membership_endpoint = "transitiveMemberOf" if transitive else "memberOf"

    url = (
        f"{GRAPH_BASE_URL}/users/{user_id}/{membership_endpoint}/microsoft.graph.group"
        "?$select=id,displayName"
        "&$top=999"
    )

    group_names: list[str] = []

    while url:
        response = client.get(url, headers=headers)
        response.raise_for_status()

        data = response.json()

        for group in data.get("value", []):
            display_name = group.get("displayName")
            if display_name:
                group_names.append(display_name)

        url = data.get("@odata.nextLink")

    return sorted(set(group_names))


def looks_like_service_account(user: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []

    values_to_check = {
        "userPrincipalName": user.get("userPrincipalName"),
        "onPremisesSamAccountName": user.get("onPremisesSamAccountName"),
    }

    for field_name, value in values_to_check.items():
        if not isinstance(value, str) or not value.strip():
            continue

        normalized = value.lower().strip()
        local_part = normalized.split("@", 1)[0]

        for pattern in SERVICE_ACCOUNT_PATTERNS:
            if re.search(pattern, local_part):
                reasons.append(f"{field_name}_matches:{pattern}")
                break

    password_policies = user.get("passwordPolicies") or ""
    if "DisablePasswordExpiration" in password_policies:
        reasons.append("password_never_expires")

    return len(reasons) > 0, reasons


def classify_user(user: dict, inactive_cutoff: datetime) -> dict:
    is_service_candidate, service_reasons = looks_like_service_account(user)

    last_login_at, last_login_source = get_best_last_login(user)
    last_login_dt = parse_graph_datetime(last_login_at)

    inactive_over_90_days = (
        last_login_dt is not None and last_login_dt < inactive_cutoff
    )

    last_login_missing = last_login_dt is None

    included_because: list[str] = []

    if is_service_candidate:
        included_because.append("service_account_candidate")

    if inactive_over_90_days:
        included_because.append("inactive_over_90_days")

    if last_login_missing:
        included_because.append("last_login_missing")

    return {
        "include": len(included_because) > 0,
        "includedBecause": included_because,
        "isServiceCandidate": is_service_candidate,
        "serviceCandidateReasons": service_reasons,
        "lastLoginAt": last_login_at,
        "lastLoginSource": last_login_source,
        "inactiveOver90Days": inactive_over_90_days,
        "lastLoginMissing": last_login_missing,
    }



def fetch_entra_users_of_interest() -> list[RawAccount]:
    token = get_graph_token()

    headers = {
        "Authorization": f"Bearer {token}",
    }

    select_fields = [
        "id",
        "displayName",
        "userPrincipalName",
        "mailNickname",
        "accountEnabled",
        "onPremisesSamAccountName",
        "passwordPolicies",
        "signInActivity",
    ]

    url = httpx.URL(
        f"{GRAPH_BASE_URL}/users",
        params={
            "$select": ",".join(select_fields),
            "$top": "500",
        },
    )

    inactive_cutoff = datetime.now(timezone.utc) - timedelta(days=90) #change cutoff point

    accounts: list[RawAccount] = []
    scanned_count = 0
    skipped_disabled_count = 0
    included_count = 0

    with httpx.Client(timeout=120) as client:
        page_number = 0

        while url:
            page_number += 1

            response = client.get(str(url), headers=headers)
            response.raise_for_status()

            data = response.json()
            users = data.get("value", [])

            for user in users:
                scanned_count += 1

                # Skip disabled accounts
                if user.get("accountEnabled") is False:
                    skipped_disabled_count += 1
                    continue

                classification = classify_user(
                    user=user,
                    inactive_cutoff=inactive_cutoff,
                )

                if not classification["include"]:
                    continue

                included_count += 1

                # group_names = fetch_user_group_names(
                #     client=client,
                #     headers=headers,
                #     user_id=user["id"],
                #     transitive=False,
                # )

                raw = {
                    **user,
                    **classification,
                    # "groupMembershipNames": group_names,
                    # "groupMembershipCount": len(group_names),
                }

                account_type = "entra_user"

                is_inactive = classification["inactiveOver90Days"]
                is_service = classification["isServiceCandidate"]
                missing_login = classification["lastLoginMissing"]

                if is_service and is_inactive:
                    account_type = "entra_user_service_candidate_inactive"
                elif is_service and missing_login:
                    account_type = "entra_user_service_candidate_missing_login"
                elif is_service:
                    account_type = "entra_user_service_candidate"
                elif is_inactive:
                    account_type = "entra_user_inactive"
                elif missing_login:
                    account_type = "entra_user_missing_login"

                accounts.append(
                    RawAccount(
                        source="ENTRA",
                        source_object_id=user["id"],
                        name=(
                            user.get("onPremisesSamAccountName")
                            or user.get("mailNickname")
                            or user.get("userPrincipalName")
                        ),
                        display_name=user.get("displayName"),
                        enabled=user.get("accountEnabled"),
                        account_type=account_type,
                        last_seen=classification["lastLoginAt"],
                        raw=raw,
                    )
                )

            url = data.get("@odata.nextLink")

            print(
                f"Fetched page {page_number}. "
                f"Scanned: {scanned_count}. "
                f"Skipped disabled: {skipped_disabled_count}. "
                f"Included: {included_count}."
            )

    return accounts








################################################################

def fetch_entra_app_identities() -> list[RawAccount]:
    token = get_graph_token()

    headers = {
        "Authorization": f"Bearer {token}",
    }

    url = (
        "https://graph.microsoft.com/v1.0/servicePrincipals"
        "?$select=id,appId,displayName,accountEnabled,servicePrincipalType,tags"
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