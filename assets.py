def parse_assets(value: str) -> tuple[str, ...]:
    assets = []
    for item in value.split(","):
        asset = item.strip().upper()
        if asset and asset not in assets:
            assets.append(asset)
    return tuple(assets)
