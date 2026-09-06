import asyncio
import json
import logging

import httpx
import pytest

from workeringestion.services import poller


async def test_poll_once_archives_raw_json_before_any_parsing(mock_httpx, mock_blob):
    await poller.poll_once("SITE001")

    assert len(mock_blob) == 1
    upload = mock_blob[0]
    assert upload["name"].startswith("brute_data/")
    assert upload["overwrite"] is False
    archived = json.loads(upload["data"])
    assert archived["site_id"] == "SITE001"
    assert archived["data_quality"] == "good"


async def test_poll_once_preserves_null_fields_in_the_archived_payload(mock_httpx, mock_blob):
    # SITE003 est "critical" dans la fixture : tous les champs de mesure sont
    # null. C'est exactement ce que le ticket demande de ne jamais perdre.
    await poller.poll_once("SITE003")

    archived = json.loads(mock_blob[0]["data"])
    assert archived["data_quality"] == "critical"
    assert archived["consumption_kw"] is None
    assert archived["null_reasons"] == ["network_loss"]


async def test_poll_once_logs_the_reading_for_a_known_site(mock_httpx, mock_blob, caplog):
    with caplog.at_level(logging.INFO, logger="workeringestion.services.poller"):
        await poller.poll_once("SITE001")

    assert any("SITE001" in record.message for record in caplog.records)


async def test_poll_once_does_not_archive_when_site_unknown(mock_httpx, mock_blob):
    await poller.poll_once("UNKNOWN")

    assert mock_blob == []


async def test_poll_once_logs_a_warning_and_does_not_raise_when_site_unknown(
    mock_httpx, mock_blob, caplog
):
    with caplog.at_level(logging.WARNING, logger="workeringestion.services.poller"):
        await poller.poll_once("UNKNOWN")

    assert any(
        record.levelname == "WARNING" and "UNKNOWN" in record.message
        for record in caplog.records
    )


async def test_poll_all_sites_polls_every_known_site(mock_httpx, mock_blob):
    await poller.poll_all_sites()

    archived_sites = {json.loads(u["data"])["site_id"] for u in mock_blob}
    assert archived_sites == {"SITE001", "SITE002", "SITE003"}
    assert len(mock_blob) == 3


async def test_poll_all_sites_continues_when_one_site_fails(mock_httpx, mock_blob, monkeypatch):
    async def failing_poll_once(site_id):
        if site_id == "SITE002":
            raise RuntimeError("boom")
        return await real_poll_once(site_id)

    real_poll_once = poller.poll_once
    monkeypatch.setattr(poller, "poll_once", failing_poll_once)

    await poller.poll_all_sites()

    archived_sites = {json.loads(u["data"])["site_id"] for u in mock_blob}
    assert archived_sites == {"SITE001", "SITE003"}  # SITE002 a échoué, les autres continuent


async def test_poll_sites_once_archives_the_raw_reference(mock_httpx, mock_blob):
    await poller.poll_sites_once()

    assert len(mock_blob) == 1
    upload = mock_blob[0]
    assert upload["name"].startswith("sites/")
    archived = json.loads(upload["data"])
    assert [site["site_id"] for site in archived] == ["SITE001", "SITE002", "SITE003"]
    assert archived[0]["capacity_kw"] == 200.0
    assert archived[0]["status"] == "active"


async def test_poll_sites_once_logs_how_many_sites_were_archived(mock_httpx, mock_blob, caplog):
    with caplog.at_level(logging.INFO, logger="workeringestion.services.poller"):
        await poller.poll_sites_once()

    assert any("3 site" in record.getMessage() for record in caplog.records)


async def test_sites_loop_fetches_once_at_startup_then_waits_a_day(
    mock_httpx, mock_blob, monkeypatch
):
    slept: list[int] = []

    async def stop_after_first_cycle(seconds):
        slept.append(seconds)
        raise StopAsyncIteration

    monkeypatch.setattr(poller.asyncio, "sleep", stop_after_first_cycle)

    try:
        await poller.sites_loop()
    except StopAsyncIteration:
        pass

    assert len(mock_blob) == 1      
    assert slept == [poller.SITES_POLL_INTERVAL_SECONDS]
    assert poller.SITES_POLL_INTERVAL_SECONDS == 86400


async def test_sites_loop_logs_and_survives_a_non_200(mock_httpx, mock_blob, monkeypatch, caplog):
    async def failing_get_sites_raw():
        return httpx.Response(
            503, json={"detail": "unavailable"},
            request=httpx.Request("GET", "http://mock-api.test/api/v1/sites"),
        )

    async def stop_after_first_cycle(_seconds):
        raise StopAsyncIteration

    monkeypatch.setattr(poller.mock_api, "get_sites_raw", failing_get_sites_raw)
    monkeypatch.setattr(poller.asyncio, "sleep", stop_after_first_cycle)

    with caplog.at_level(logging.ERROR, logger="workeringestion.services.poller"):
        try:
            await poller.sites_loop()
        except StopAsyncIteration:
            pass

    assert mock_blob == []
    assert any("référentiel" in record.getMessage() for record in caplog.records)


async def test_sites_loop_logs_and_survives_a_network_error(
    mock_httpx, mock_blob, monkeypatch, caplog
):
    async def unreachable():
        raise httpx.ConnectError("Connection refused")

    async def stop_after_first_cycle(_seconds):
        raise StopAsyncIteration

    monkeypatch.setattr(poller.mock_api, "get_sites_raw", unreachable)
    monkeypatch.setattr(poller.asyncio, "sleep", stop_after_first_cycle)

    with caplog.at_level(logging.ERROR, logger="workeringestion.services.poller"):
        try:
            await poller.sites_loop()
        except StopAsyncIteration:
            pass

    assert mock_blob == []
    assert any("référentiel" in record.getMessage() for record in caplog.records)


async def test_measurements_keep_flowing_when_the_sites_loop_fails(
    mock_httpx, mock_blob, monkeypatch, caplog
):

    real_sleep = asyncio.sleep

    async def failing_sites():
        raise httpx.ConnectError("Connection refused")

    async def stop_after_first_cycle(_seconds):
        await real_sleep(0)
        raise StopAsyncIteration

    monkeypatch.setattr(poller, "poll_sites_once", failing_sites)
    monkeypatch.setattr(poller.asyncio, "sleep", stop_after_first_cycle)

    with caplog.at_level(logging.ERROR, logger="workeringestion.services.poller"):
        with pytest.raises(StopAsyncIteration):
            await asyncio.gather(poller.poll_loop(), poller.sites_loop())

    assert {json.loads(u["data"])["site_id"] for u in mock_blob} == {
        "SITE001", "SITE002", "SITE003",
    }
    assert any("référentiel" in record.getMessage() for record in caplog.records)


async def test_poll_all_sites_falls_back_to_the_last_known_list(
    mock_httpx, mock_blob, monkeypatch, caplog
):
    await poller.poll_all_sites()
    assert len(mock_blob) == 3

    async def unreachable():
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(poller.mock_api, "list_site_ids", unreachable)

    with caplog.at_level(logging.WARNING, logger="workeringestion.services.poller"):
        await poller.poll_all_sites()

    assert len(mock_blob) == 6
    assert any("dernière liste connue" in r.getMessage() for r in caplog.records)


async def test_poll_all_sites_does_not_cache_a_failed_lookup(
    mock_httpx, mock_blob, monkeypatch
):
    async def unreachable():
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(poller.mock_api, "list_site_ids", unreachable)
    await poller.poll_all_sites()

    assert poller._last_known_site_ids == []


async def test_poll_all_sites_polls_nothing_on_a_cold_start_failure(
    mock_httpx, mock_blob, monkeypatch, caplog
):

    async def unreachable():
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(poller.mock_api, "list_site_ids", unreachable)

    with caplog.at_level(logging.WARNING, logger="workeringestion.services.poller"):
        await poller.poll_all_sites()

    assert mock_blob == []
    assert any("(0 sites)" in r.getMessage() for r in caplog.records)


async def test_poll_all_sites_refreshes_the_cache_on_every_success(mock_httpx, mock_blob):
    await poller.poll_all_sites()

    assert poller._last_known_site_ids == ["SITE001", "SITE002", "SITE003"]
