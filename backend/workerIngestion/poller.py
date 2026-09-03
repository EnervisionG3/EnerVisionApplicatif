import asyncio
import logging
import os

from backend.workerIngestion import blob_archive, repository

logger = logging.getLogger(__name__)

# Un seul site pour l'instant (cf. ticket) — à terme, boucler sur tous les
# sites connus (backend.sites une fois branché, ou une liste dédiée).
POLL_SITE_ID = os.environ.get("POLL_SITE_ID", "SITE001")
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))


async def poll_once(site_id: str = POLL_SITE_ID) -> None:
    """Un cycle : récupère la lecture brute, l'archive telle quelle sur le
    Data Lake avant toute transformation, puis journalise un résumé.

    Passe par repository directement (pas par service.get_current_reading) :
    on a besoin du texte brut de la réponse, pas d'un EnergyReading reparsé,
    et le 404 n'est pas une erreur HTTP à faire remonter ici, juste un état à
    journaliser.
    """
    response = await repository.get_current_reading_raw(site_id)

    if response.status_code == 404:
        logger.warning("Site '%s' introuvable lors du polling", site_id)
        return
    response.raise_for_status()

    blob_name = await blob_archive.archive_raw(response.text)

    data_quality = response.json().get("data_quality")
    logger.info(
        "Lecture archivée pour %s (data_quality=%s) -> %s",
        site_id,
        data_quality,
        blob_name,
    )


async def poll_loop() -> None:
    while True:
        try:
            await poll_once()
        except Exception:
            logger.exception("Erreur pendant le polling de %s", POLL_SITE_ID)

        await asyncio.sleep(POLL_INTERVAL_SECONDS)
