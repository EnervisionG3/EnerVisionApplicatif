import asyncio
import logging
import os

from workeringestion.api import blob_storage, mock_api

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))

SITES_POLL_INTERVAL_SECONDS = int(os.environ.get("SITES_POLL_INTERVAL_SECONDS", "86400"))


async def poll_once(site_id: str) -> None:
    """Un cycle pour un site : lit, archive brut, logue. Passe par mock_api
    directement (texte brut requis, pas un modèle reparsé)."""
    response = await mock_api.get_current_reading_raw(site_id)

    if response.status_code == 404:
        logger.warning("Site '%s' introuvable lors du polling", site_id)
        return
    response.raise_for_status()

    blob_name = await blob_storage.archive_raw(response.text)

    data_quality = response.json().get("data_quality")
    logger.info(
        "Lecture archivée pour %s (data_quality=%s) -> %s",
        site_id,
        data_quality,
        blob_name,
    )

_last_known_site_ids: list[str] = []


async def poll_all_sites() -> None:
    global _last_known_site_ids
    try:
        site_ids = await mock_api.list_site_ids()
        _last_known_site_ids = site_ids
    except Exception:
        logger.warning(
            "Impossible de récupérer la liste des sites — "
            "utilisation de la dernière liste connue (%d sites).",
            len(_last_known_site_ids),
        )
        site_ids = _last_known_site_ids

    for site_id in site_ids:
        try:
            await poll_once(site_id)
        except Exception:
            logger.exception("Erreur pendant le polling de %s", site_id)


async def poll_loop() -> None:
    while True:
        try:
            await poll_all_sites()
        except Exception:
            logger.exception("Erreur pendant le cycle de polling")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def poll_sites_once() -> None:
    response = await mock_api.get_sites_raw()
    response.raise_for_status()

    blob_name = await blob_storage.archive_sites_raw(response.text)

    logger.info("%d site(s) archivé(s) -> %s", len(response.json()), blob_name)


async def sites_loop() -> None:
    while True:
        try:
            await poll_sites_once()
        except Exception:
            logger.exception("Erreur pendant la récupération du référentiel des sites")

        await asyncio.sleep(SITES_POLL_INTERVAL_SECONDS)
