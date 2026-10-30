"""Cache transport requirements protect OAuth single-use state and shared rate-limit counters."""

import asyncio


async def test_bytes_round_trip_and_repeated_delete(byte_store):
    assert await byte_store.get("missing") is None
    await byte_store.put("data", b"\x00\xffpayload", ttl_seconds=30)
    assert await byte_store.get("data") == b"\x00\xffpayload"

    await byte_store.delete("data")
    await byte_store.delete("data")
    assert await byte_store.get("data") is None


async def test_put_if_absent_has_one_winner_without_overwriting_it(byte_store):
    values = [f"candidate-{index}".encode() for index in range(16)]
    outcomes = await asyncio.gather(
        *(byte_store.put_if_absent("claim", value, ttl_seconds=30) for value in values)
    )

    assert sum(outcomes) == 1
    assert await byte_store.get("claim") == values[outcomes.index(True)]


async def test_take_consumes_a_value_only_once_under_concurrent_access(byte_store):
    await byte_store.put("oauth-state", b"verified-state", ttl_seconds=30)

    results = await asyncio.gather(*(byte_store.take("oauth-state") for _ in range(16)))

    assert results.count(b"verified-state") == 1
    assert results.count(None) == 15
    assert await byte_store.get("oauth-state") is None


async def test_window_increment_is_atomic(byte_store):
    results = await asyncio.gather(
        *(byte_store.increment_window("rate", 30) for _ in range(16))
    )
    assert sorted(count for count, _ in results) == list(range(1, 17))
    assert all(0 < ttl <= 30 for _, ttl in results)


async def test_existing_window_is_not_extended_and_restarts_after_expiry(byte_store):
    assert (await byte_store.increment_window("rate", 1))[0] == 1
    count, ttl = await byte_store.increment_window("rate", 30)
    assert count == 2
    assert (
        0 <= ttl <= 1
    )  # Later requests must not turn a fixed window into a sliding one.

    # Wait for observed expiry rather than asserting against an exact scheduler delay.
    async with asyncio.timeout(5):
        while await byte_store.get("rate") is not None:
            await asyncio.sleep(0.05)
    count, ttl = await byte_store.increment_window("rate", 30)
    assert count == 1
    assert 0 < ttl <= 30
