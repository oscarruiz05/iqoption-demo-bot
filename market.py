def filter_open_assets(open_times: dict, configured_assets: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return configured assets that are open for turbo or binary options."""
    turbo = open_times.get("turbo", {})
    binary = open_times.get("binary", {})
    opened = []
    unavailable = []

    for asset in configured_assets:
        is_open = bool(turbo.get(asset, {}).get("open") or binary.get(asset, {}).get("open"))
        (opened if is_open else unavailable).append(asset)

    return tuple(opened), tuple(unavailable)
