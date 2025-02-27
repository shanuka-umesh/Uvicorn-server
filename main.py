import time
import os
import platform
import psutil
import asyncio
import logging
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from fastapi.middleware.gzip import GZipMiddleware

# Create logs directory if it doesn't exist
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# Configure logging
LOG_FILE = os.path.join(LOG_DIR, "server.log")

logging.basicConfig(
    level=logging.NOTSET,  # Capture all log levels
    format="%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(funcName)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Enable logging for all dependencies
for logger_name in logging.root.manager.loggerDict:
    logging.getLogger(logger_name).setLevel(logging.NOTSET)

# FastAPI Application
app = FastAPI()
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Rate Limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# Static Files & Templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DUMMY_PRODUCTS = [
    {"id": 1, "name": "Laptop", "price": 1500, "description": "A high-performance laptop"},
    {"id": 2, "name": "Smartphone", "price": 800, "description": "A smartphone with a great camera"},
    {"id": 3, "name": "Headphones", "price": 200, "description": "Noise-canceling headphones"},

]

logger.info("FastAPI Application is starting...")

# Server Resource Usage Logging
async def log_server_stats():
    process = psutil.Process(os.getpid())
    while True:
        cpu_usage = process.cpu_percent(interval=1)
        memory_info = process.memory_info().rss / (1024 ** 2)  # Convert to MB
        logger.debug(f"Server Stats: CPU {cpu_usage}% | Memory {memory_info:.2f}MB")
        await asyncio.sleep(30)

# Use FastAPI lifespan for startup and shutdown
@app.on_event("startup")
async def startup_event():
    logger.info("Server is starting...")
    system_info = {
        "OS": platform.system(),
        "OS Version": platform.version(),
        "Processor": platform.processor(),
        "CPU Cores": psutil.cpu_count(logical=True),
        "Memory": f"{round(psutil.virtual_memory().total / (1024 ** 3), 2)} GB",
        "Python Version": platform.python_version(),
    }
    logger.debug(f"System Info: {system_info}")
    asyncio.create_task(log_server_stats())

@app.on_event("shutdown")
def shutdown_event():
    logger.info("Application is shutting down...")

# Middleware for Logging Requests & Responses
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    client_ip = request.client.host if request.client else "Unknown"
    logger.info(f" Incoming Request: {request.method} {request.url} from {client_ip}")
    logger.debug(f"Headers: {dict(request.headers)}")

    try:
        request_body = await request.body()
        if request_body:
            logger.debug(f"Request Body: {request_body.decode('utf-8', errors='ignore')}")
    except Exception:
        logger.debug("Unable to read request body")

    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(f"Error processing request: {str(exc)}", exc_info=True)
        return JSONResponse(content={"error": "Internal server error"}, status_code=500)

    duration = time.time() - start_time
    logger.info(f"Response Sent: {response.status_code} (Processed in {duration:.4f} seconds)")
    logger.debug(f"Response Headers: {dict(response.headers)}")
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

# Run Uvicorn Server with Improved Logging
if __name__ == "__main__":
    logger.info("Starting Uvicorn server...")
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_config=None,
        log_level="trace",
        access_log=True,
    )
