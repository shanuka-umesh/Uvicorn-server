import logging
import time
import os
import platform
import psutil  # System monitoring
import asyncio
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

# Log file setup
LOG_FILE = "logs/server.log"

# Configure logging (capture both FastAPI and Uvicorn logs)
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.DEBUG,  # Capture ALL logs
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)

# Capture Uvicorn logs
uvicorn_logger = logging.getLogger("uvicorn")
uvicorn_logger.setLevel(logging.DEBUG)
uvicorn_logger.addHandler(logging.FileHandler(LOG_FILE))

# Capture system logs (CPU, Memory)
def log_system_stats():
    while True:
        cpu_usage = psutil.cpu_percent(interval=1)
        memory_info = psutil.virtual_memory()
        disk_usage = psutil.disk_usage("/")
        logging.info(
            f"System Stats: CPU: {cpu_usage}% | RAM: {memory_info.percent}% | Disk: {disk_usage.percent}%"
        )
        time.sleep(60)  # Log every 60 seconds

# Run system stats logger in the background
async def start_logging_system_stats():
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, log_system_stats)

# FastAPI app setup
app = FastAPI()

# Static files & templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DUMMY_PRODUCTS = [
    {"id": 1, "name": "Laptop", "price": 1500, "description": "A high-performance laptop"},
    {"id": 2, "name": "Smartphone", "price": 800, "description": "A smartphone with a great camera"},
    {"id": 3, "name": "Headphones", "price": 200, "description": "Noise-canceling headphones"},
]

logging.info("FastAPI Application is starting...")

# Log server details on startup
@app.on_event("startup")
async def startup_event():
    logging.info("Server is starting...")
    system_info = {
        "OS": platform.system(),
        "OS Version": platform.version(),
        "Processor": platform.processor(),
        "CPU Cores": psutil.cpu_count(logical=True),
        "Memory": f"{round(psutil.virtual_memory().total / (1024 ** 3), 2)} GB",
        "Python Version": platform.python_version(),
        "Environment Variables": dict(os.environ),
    }
    logging.info(f"System Info: {system_info}")
    await start_logging_system_stats()  # Start system stats logging

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()

    logging.info(f"Request: {request.method} {request.url}")
    logging.debug(f"Headers: {dict(request.headers)}")

    try:
        request_body = await request.body()
        if request_body:
            logging.debug(f"Request Body: {request_body.decode('utf-8')}")
    except Exception:
        logging.debug("Unable to read request body")

    response = await call_next(request)

    duration = time.time() - start_time
    logging.info(f"Response: {response.status_code} (Processed in {duration:.4f} seconds)")
    return response

# Controller
@app.get("/")
def home(request: Request, name: str = "Guest"):
    logging.info(f"Processing homepage request with name: {name}")
    return templates.TemplateResponse("index.html", {"request": request, "products": DUMMY_PRODUCTS, "name": name})


@app.get("/product/{product_id}")
def product_detail(request: Request, product_id: int):
    logging.info(f"Processing product request: ID {product_id}")
    product = next((p for p in DUMMY_PRODUCTS if p["id"] == product_id), None)

    if product is None:
        logging.warning(f" Product ID {product_id} not found")
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    return templates.TemplateResponse("product.html", {"request": request, "product": product})

@app.post("/add-to-cart/{product_id}")
async def add_to_cart(product_id: int):
    product = next((p for p in DUMMY_PRODUCTS if p["id"] == product_id), None)

    if product is None:
        logging.warning(f"Add to Cart failed: Product ID {product_id} not found")
        return JSONResponse(content={"error": "Product not found"}, status_code=404)

    logging.info(f"Product added to cart: {product['name']} (ID: {product_id})")

    return JSONResponse(content={"message": f"Added {product['name']} to cart!"}, status_code=200)


# Catch undefined routes
@app.get("/{full_path:path}")
def catch_all(request: Request, full_path: str):
    logging.warning(f" Undefined route accessed: {full_path}")
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f" Unhandled error: {str(exc)}", exc_info=True)
    return templates.TemplateResponse("404.html", {"request": request}, status_code=500)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled error: {str(exc)}", exc_info=True)
    return JSONResponse(content={"error": "Internal server error"}, status_code=500)

# Log application shutdown
@app.on_event("shutdown")
def shutdown_event():
    logging.info("Application is shutting down...")

# Run Uvicorn server with all logs enabled
if __name__ == "__main__":
    logging.info("Starting Uvicorn server...")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug",  # Enable all logs
        access_log=True,  # Log every request/response
    )
