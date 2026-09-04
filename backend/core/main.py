from fastapi import FastAPI

from core.api.controller.measurement import router as measurement_router
from core.api.controller.site import router as site_router
from core.api.routes import router as core_router

app = FastAPI(
    title="EnerVision API",
    description="API EnerVision — supervision de la consommation énergétique des sites.",
    version="1.0.0",
)

app.include_router(core_router)
app.include_router(site_router)
app.include_router(measurement_router)
