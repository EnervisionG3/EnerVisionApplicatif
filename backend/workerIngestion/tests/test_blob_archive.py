import re

from backend.workerIngestion import blob_archive

_BLOB_NAME_PATTERN = re.compile(
    r"^brute_data/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json$"
)


async def test_archive_raw_uploads_the_exact_text_given(mock_blob):
    raw_json = '{"site_id": "SITE001", "consumption_kw": null}'

    blob_name = await blob_archive.archive_raw(raw_json)

    assert len(mock_blob) == 1
    assert mock_blob[0]["name"] == blob_name
    assert mock_blob[0]["data"] == raw_json  # texte inchangé, pas reparsé
    assert mock_blob[0]["overwrite"] is False


async def test_archive_raw_writes_flat_under_brute_data_with_a_unique_name(mock_blob):
    await blob_archive.archive_raw('{"a": 1}')
    await blob_archive.archive_raw('{"a": 2}')

    names = [upload["name"] for upload in mock_blob]
    assert all(_BLOB_NAME_PATTERN.match(name) for name in names)
    assert len(set(names)) == 2  # pas de collision entre deux écritures
