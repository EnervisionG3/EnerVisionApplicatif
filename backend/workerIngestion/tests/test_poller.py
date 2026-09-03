import json
import logging

from backend.workerIngestion import poller


async def test_poll_once_archives_raw_json_before_any_parsing(mock_httpx, mock_blob):
    await poller.poll_once("SITE001")

    assert len(mock_blob) == 1
    upload = mock_blob[0]
    assert upload["name"].startswith("brute_data/")
    assert upload["overwrite"] is False
    # Le texte archivé doit être le JSON brut, pas un modèle Pydantic reformaté.
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
    with caplog.at_level(logging.INFO, logger="backend.workerIngestion.poller"):
        await poller.poll_once("SITE001")

    assert any("SITE001" in record.message for record in caplog.records)


async def test_poll_once_does_not_archive_when_site_unknown(mock_httpx, mock_blob):
    await poller.poll_once("UNKNOWN")

    assert mock_blob == []


async def test_poll_once_logs_a_warning_and_does_not_raise_when_site_unknown(
    mock_httpx, mock_blob, caplog
):
    with caplog.at_level(logging.WARNING, logger="backend.workerIngestion.poller"):
        await poller.poll_once("UNKNOWN")

    assert any(
        record.levelname == "WARNING" and "UNKNOWN" in record.message
        for record in caplog.records
    )
