from backend.workerIngestion import repository
from backend.workerIngestion.schemas import EnergyReading


async def test_get_current_reading_returns_matching_reading(mock_httpx):
    reading = await repository.get_current_reading("SITE001")

    assert isinstance(reading, EnergyReading)
    assert reading.data_quality == "good"


async def test_get_current_reading_keeps_null_fields_for_partial_quality(mock_httpx):
    reading = await repository.get_current_reading("SITE002")

    assert reading.data_quality == "partial"
    assert reading.temperature_celsius is None
    assert reading.null_reasons == ["temperature_sensor_failure"]


async def test_get_current_reading_keeps_all_null_fields_for_critical_quality(mock_httpx):
    reading = await repository.get_current_reading("SITE003")

    assert reading.data_quality == "critical"
    assert reading.consumption_kw is None
    assert reading.null_reasons == ["network_loss"]


async def test_get_current_reading_returns_none_when_unknown(mock_httpx):
    assert await repository.get_current_reading("UNKNOWN") is None


async def test_get_current_reading_raw_returns_response_with_raw_text(mock_httpx):
    response = await repository.get_current_reading_raw("SITE001")

    assert response.status_code == 200
    # Le texte brut doit rester du JSON exploitable tel quel, sans passer par
    # un modèle Pydantic.
    assert response.json()["site_id"] == "SITE001"


async def test_get_current_reading_raw_does_not_normalize_404(mock_httpx):
    response = await repository.get_current_reading_raw("UNKNOWN")

    # Contrairement à get_current_reading, pas de None ici : le 404 est
    # relayé tel quel, à l'appelant de décider quoi en faire.
    assert response.status_code == 404
