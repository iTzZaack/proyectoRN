"""
logger.py
Logging simple para depurar el pipeline sin exponer credenciales.
"""
import datetime


def log(module: str, message: str):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{module}] {message}")
