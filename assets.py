def parse_assets(value: str) -> tuple[str, ...]:
    assets = []
    for item in value.split(","):
        asset = item.strip().upper()
        if asset and asset not in assets:
            assets.append(asset)
    return tuple(assets)


def rejection_cooldown_seconds(reason) -> int:
    text = str(reason).lower()
    if "suspended" in text or "not open" in text or "closed" in text:
        return 900
    return 300
