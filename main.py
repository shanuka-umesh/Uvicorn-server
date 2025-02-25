from loguru import logger
import time
import os
import platform
import psutil  # For system monitoring
import asyncio
import uvicorn
from fastapi import FastAPI, Request, Response, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi.middleware.gzip import GZipMiddleware

# Create logs directory if not exists
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Configure Loguru Logging
LOG_FILE = os.path.join(LOG_DIR, "server.log")
logger.remove()
logger.add(LOG_FILE, level="TRACE", format="{time} - {level} - {message}")
logger.add("sys.stderr", level="DEBUG", format="{time} - {level} - {message}")

# FastAPI Application
app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Rate Limiting
limiter = Limiter(key_func=get_remote_address)

# Static Files & Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DUMMY_PRODUCTS = [
    {"id": 1, "name": "Laptop", "price": 1500, "description": "A high-performance laptop"},
    {"id": 2, "name": "Smartphone", "price": 800, "description": "A smartphone with a great camera"},
    {"id": 3, "name": "Headphones", "price": 200, "description": "Noise-canceling headphones"},
]

logger.info("FastAPI Application is starting...")

# System Stats Logging
async def log_system_stats():
    while True:

        cpu_usage = psutil.cpu_percent(interval=1)
        memory_info = psutil.virtual_memory()
        disk_usage = psutil.disk_usage("/")
        logger.info(f"System Stats: CPU {cpu_usage}% | RAM {memory_info.percent}% | Disk {disk_usage.percent}%")
        await asyncio.sleep(60)  # Non-blocking sleep

# Startup Event
@app.on_event("startup")
async def startup_event():
    logger.info(" Server is starting...")
    system_info = {
        "OS": platform.system(),
        "OS Version": platform.version(),
        "Processor": platform.processor(),
        "CPU Cores": psutil.cpu_count(logical=True),
        "Memory": f"{round(psutil.virtual_memory().total / (1024 ** 3), 2)} GB",
        "Python Version": platform.python_version(),
    }
    logger.info(f"System Info: {system_info}")
    asyncio.create_task(log_system_stats())  # Start non-blocking system monitoring

# Middleware for Logging Requests & Responses
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"➡ Incoming Request: {request.method} {request.url}")
    logger.debug(f"Headers: {dict(request.headers)}")

    try:
        request_body = await request.body()
        if request_body:
            logger.debug(f"Request Body: {request_body.decode('utf-8')}")
    except Exception:
        logger.debug("Unable to read request body")

    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(f"Error processing request: {str(exc)}", exc_info=True)
        return JSONResponse(content={"error": "Internal server error"}, status_code=500)

    duration = time.time() - start_time
    logger.info(f"Response Sent: {response.status_code} (Processed in {duration:.4f} seconds)")
    return response

# Homepage Route
@app.get("/")
def home(request: Request, name: str = "Guest"):
    logger.info(f"Processing homepage request with name: {name}")
    return templates.TemplateResponse("index.html", {"request": request, "products": DUMMY_PRODUCTS, "name": name})

# Product Details Route
@app.get("/product/{product_id}")
def product_detail(request: Request, product_id: int):
    logger.info(f"Fetching Product: ID {product_id}")
    product = next((p for p in DUMMY_PRODUCTS if p["id"] == product_id), None)

    if product is None:
        logger.warning(f"Product ID {product_id} not found")
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    return templates.TemplateResponse("product.html", {"request": request, "product": product})

# Add to Cart Route
@app.post("/add-to-cart/{product_id}")
@limiter.limit("5/minute")
async def add_to_cart(request: Request, product_id: int):
    product = next((p for p in DUMMY_PRODUCTS if p["id"] == product_id), None)

    if product is None:
        logger.warning(f"Add to Cart failed: Product ID {product_id} not found")
        return JSONResponse(content={"error": "Product not found"}, status_code=404)

    logger.info(f"Product added to cart: {product['name']} (ID: {product_id})")
    return JSONResponse(content={"message": f"Added {product['name']} to cart!"}, status_code=200)

# Catch-All Undefined Routes
@app.get("/{full_path:path}")
def catch_all(request: Request, full_path: str):
    logger.warning(f"Undefined Route Accessed: {full_path}")
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled Exception: {str(exc)}", exc_info=True)
    return JSONResponse(content={"error": "Internal server error"}, status_code=500)

# Shutdown Event Logging
@app.on_event("shutdown")
def shutdown_event():
    logger.info("Application is shutting down...")

# Run Uvicorn Server with Advanced Logging
if __name__ == "__main__":
    logger.info("Starting Uvicorn server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug",
        access_log=True,
    )
