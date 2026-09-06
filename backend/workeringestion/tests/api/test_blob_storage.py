import logging
from datetime import datetime, timezone

from azure.core.exceptions import ResourceExistsError

from workeringestion.api import blob_storage


async def test_archive_raw_uploads_and_returns_the_blob_name(mock_blob):
    blob_name = await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert blob_name.startswith("brute_data/")
    assert mock_blob[0]["name"] == blob_name
    assert mock_blob[0]["data"] == '{"site_id": "SITE001"}'


async def test_archive_raw_logs_a_warning_and_does_not_raise_on_name_collision(
    monkeypatch, caplog
):
    async def fake_upload_blob(name, data, overwrite=False):
        raise ResourceExistsError("The specified blob already exists.")

    monkeypatch.setattr(blob_storage._container_client, "upload_blob", fake_upload_blob)

    with caplog.at_level(logging.WARNING, logger="workeringestion.api.blob_storage"):
        blob_name = await blob_storage.archive_raw('{"site_id": "SITE001"}')

    assert blob_name.startswith("brute_data/")
    assert any(
        record.levelname == "WARNING" and "déjà existant" in record.message
        for record in caplog.records
    )


async def test_archive_sites_raw_writes_under_the_sites_prefix(mock_blob):
    blob_name = await blob_storage.archive_sites_raw('[{"site_id": "SITE001"}]')

    assert blob_name.startswith("sites/")
    assert mock_blob[0]["name"] == blob_name
    assert mock_blob[0]["data"] == '[{"site_id": "SITE001"}]'
    assert mock_blob[0]["overwrite"] is False


async def test_archive_sites_raw_puts_the_fetch_date_in_the_blob_name(mock_blob):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    blob_name = await blob_storage.archive_sites_raw('[{"site_id": "SITE001"}]')

    assert blob_name.startswith(f"sites/{today}-")


async def test_archive_sites_raw_never_collides_within_the_same_day(mock_blob):
    first = await blob_storage.archive_sites_raw('[]')
    second = await blob_storage.archive_sites_raw('[]')

    assert first != second


async def test_sites_are_not_written_where_the_etl_reads_measurements(mock_blob):
    blob_name = await blob_storage.archive_sites_raw('[{"site_id": "SITE001"}]')

    assert not blob_name.startswith("brute_data/")
