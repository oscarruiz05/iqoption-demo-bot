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


def is_connection_error(error) -> bool:
    text = str(error).lower()
    markers = (
        "reconnect", "connection", "websocket", "getaddrinfo",
        "timed out", "timeout", "winerror 10054",
    )
    return isinstance(error, (ConnectionError, TimeoutError)) or any(
        marker in text for marker in markers
    )


def next_asset_batch(
    assets: tuple[str, ...], cursor: int, batch_size: int
) -> tuple[tuple[str, ...], int]:
    """Return a round-robin batch without querying every asset in one burst."""
    if not assets:
        return (), 0
    count = min(batch_size, len(assets))
    batch = tuple(assets[(cursor + index) % len(assets)] for index in range(count))
    return batch, (cursor + count) % len(assets)
