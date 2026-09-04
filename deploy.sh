#!/usr/bin/env bash

set -Eeuo pipefail

readonly APP_DIR="/opt/enervisionG3"
readonly COMPOSE_FILE="${APP_DIR}/docker-compose-prod.yaml"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

error() {
    printf '[%s] ERROR: %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >&2
}

# ---------------------------------------------------------------------------
# Validation des paramètres
# ---------------------------------------------------------------------------

if [[ -z "${SERVICE:-}" ]]; then
    error "La variable SERVICE est obligatoire."
    exit 1
fi

if [[ -z "${IMAGE:-}" ]]; then
    error "La variable IMAGE est obligatoire."
    exit 1
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
    error "Fichier Docker Compose introuvable : $COMPOSE_FILE"
    exit 1
fi

# ---------------------------------------------------------------------------
# Services autorisés
# ---------------------------------------------------------------------------

case "$SERVICE" in
    authentication)
        IMAGE_VARIABLE="AUTHENTICATION_IMAGE"
        ;;
    consumption)
        IMAGE_VARIABLE="CONSUMPTION_IMAGE"
        ;;
    etl)
        IMAGE_VARIABLE="ETL_IMAGE"
        ;;
    prediction)
        IMAGE_VARIABLE="PREDICTION_IMAGE"
        ;;
    recommandation)
        IMAGE_VARIABLE="RECOMMANDATION_IMAGE"
        ;;
    health)
        IMAGE_VARIABLE="HEALTH_IMAGE"
        ;;
    *)
        error "Service non autorisé : $SERVICE"
        exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# Vérification des dépendances
# ---------------------------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
    error "Docker n'est pas installé."
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    error "Docker Compose n'est pas disponible."
    exit 1
fi

cd "$APP_DIR"

log "Déploiement du service '$SERVICE'."
log "Image cible : $IMAGE"

# ---------------------------------------------------------------------------
# Injection de l'image dans Docker Compose
# ---------------------------------------------------------------------------

export "${IMAGE_VARIABLE}=${IMAGE}"

# ---------------------------------------------------------------------------
# Récupération de l'image actuellement déployée
# ---------------------------------------------------------------------------

CURRENT_CONTAINER_ID="$(
    docker compose \
        -f "$COMPOSE_FILE" \
        ps -q "$SERVICE" 2>/dev/null || true
)"

PREVIOUS_IMAGE=""

if [[ -n "$CURRENT_CONTAINER_ID" ]]; then
    PREVIOUS_IMAGE="$(
        docker inspect \
            --format '{{.Config.Image}}' \
            "$CURRENT_CONTAINER_ID" \
            2>/dev/null || true
    )"

    if [[ -n "$PREVIOUS_IMAGE" ]]; then
        log "Image actuellement déployée : $PREVIOUS_IMAGE"
    fi
fi

# ---------------------------------------------------------------------------
# Pull de la nouvelle image
# ---------------------------------------------------------------------------

log "Téléchargement de l'image..."

MAX_RETRIES=3
RETRY_DELAY=10

for attempt in $(seq 1 "$MAX_RETRIES"); do
    if docker compose -f "$COMPOSE_FILE" pull "$SERVICE"; then
        break
    fi

    if [[ "$attempt" -eq "$MAX_RETRIES" ]]; then
        error "Impossible de télécharger l'image après ${MAX_RETRIES} tentatives : $IMAGE"
        exit 1
    fi

    log "Échec du pull, nouvelle tentative dans ${RETRY_DELAY}s (${attempt}/${MAX_RETRIES})..."
    sleep "$RETRY_DELAY"
done

# ---------------------------------------------------------------------------
# Déploiement
# ---------------------------------------------------------------------------

log "Déploiement du conteneur..."

if ! docker compose \
    -f "$COMPOSE_FILE" \
    up \
    -d \
    --no-deps \
    "$SERVICE"; then

    error "Échec du déploiement du service '$SERVICE'."

    if [[ -n "$PREVIOUS_IMAGE" ]]; then
        log "Tentative de rollback vers : $PREVIOUS_IMAGE"

        export "${IMAGE_VARIABLE}=${PREVIOUS_IMAGE}"

        if docker compose \
            -f "$COMPOSE_FILE" \
            up \
            -d \
            --no-deps \
            "$SERVICE"; then

            log "Rollback effectué avec succès."
        else
            error "Échec du rollback."
        fi
    else
        error "Aucune image précédente disponible pour effectuer un rollback."
    fi

    exit 1
fi

# ---------------------------------------------------------------------------
# Vérification du conteneur
# ---------------------------------------------------------------------------

log "Vérification de l'état du conteneur..."

sleep 3

CONTAINER_ID="$(
    docker compose \
        -f "$COMPOSE_FILE" \
        ps -q "$SERVICE"
)"

if [[ -z "$CONTAINER_ID" ]]; then
    error "Aucun conteneur trouvé pour '$SERVICE'."
    exit 1
fi

CONTAINER_STATUS="$(
    docker inspect \
        --format '{{.State.Status}}' \
        "$CONTAINER_ID"
)"

if [[ "$CONTAINER_STATUS" != "running" ]]; then
    error "Le conteneur '$SERVICE' n'est pas démarré."
    error "État actuel : $CONTAINER_STATUS"

    log "Derniers logs du conteneur :"
    docker logs --tail 50 "$CONTAINER_ID" >&2 || true

    exit 1
fi

log "Conteneur '$SERVICE' en cours d'exécution."
log "Déploiement terminé avec succès."