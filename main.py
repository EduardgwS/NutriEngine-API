from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from routes.auth_routes import auth_router
from routes.megumi_routes import megumi_router
from routes.food_routes import food_router
from routes.mercado_routes import mercado_router

app = FastAPI(title="NutriEngine API")

app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

app.include_router(auth_router)
app.include_router(megumi_router)
app.include_router(food_router)
app.include_router(mercado_router)