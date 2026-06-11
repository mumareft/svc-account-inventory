import os
from ldap3 import Server, Connection, ALL, SUBTREE
from dotenv import load_dotenv

from src.models import RawAccount

load_dotenv()


def fetch_ad_service_accounts() -> list[RawAccount]:
    server = Server(os.environ["AD_SERVER"], get_info=ALL)

    conn = Connection(
        server,
        user=os.environ["AD_BIND_USER"],
        password=os.environ["AD_BIND_PASSWORD"],
        auto_bind=True,
    )

    search_base = os.environ["AD_SEARCH_BASE"]

    # Start broad but reasonable.
    # You can tune this later based on your naming conventions.
    search_filter = (
        "(&"
        "(objectClass=user)"
        "(|"
        "(sAMAccountName=svc*)"
        "(sAMAccountName=sa*)"
        "(servicePrincipalName=*)"
        ")"
        ")"
    )

    attributes = [
        "objectGUID",
        "sAMAccountName",
        "userPrincipalName",
        "displayName",
        "description",
        "distinguishedName",
        "servicePrincipalName",
        "userAccountControl",
        "whenCreated",
        "whenChanged",
        "lastLogonTimestamp",
    ]

    conn.search(
        search_base=search_base,
        search_filter=search_filter,
        search_scope=SUBTREE,
        attributes=attributes,
    )

    accounts: list[RawAccount] = []

    for entry in conn.entries:
        raw = entry.entry_attributes_as_dict

        object_guid = str(entry.objectGUID)
        name = str(raw.get("sAMAccountName", [""])[0])

        user_account_control = int(raw.get("userAccountControl", [0])[0])
        disabled = bool(user_account_control & 2)

        accounts.append(
            RawAccount(
                source="AD",
                source_object_id=object_guid,
                name=name,
                display_name=str(raw.get("displayName", [None])[0]),
                enabled=not disabled,
                account_type="ad_user",
                last_seen=str(raw.get("lastLogonTimestamp", [None])[0]),
                raw=raw,
            )
        )

    conn.unbind()
    return accounts