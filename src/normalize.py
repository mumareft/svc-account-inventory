import re


def normalize_account_name(value: str | None) -> str | None:
    if not value:
        return None

    value = value.lower().strip()
    value = value.replace("$", "")

    # Remove domain prefix: DOMAIN\\svc-name -> svc-name
    if "\\" in value:
        value = value.split("\\", 1)[1]

    # Remove UPN suffix: svc-name@example.com -> svc-name
    if "@" in value:
        value = value.split("@", 1)[0]

    value = re.sub(r"[^a-z0-9._-]", "", value)
    return value