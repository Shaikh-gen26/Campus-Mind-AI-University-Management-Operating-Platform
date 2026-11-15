import os
from urllib.parse import urlsplit

print("APP_ENV:", os.getenv("APP_ENV", "NOT AVAILABLE"))

for name in ("DATABASE_URL", "POSTGRES_URL", "DATABASE_URL_POOLED", "PRISMA_DATABASE_URL"):
    value = os.getenv(name, "")
    parsed = urlsplit(value)
    print(f"{name} configured:", bool(parsed.hostname and parsed.path.strip("/")))
    if value:
        print(f"{name} type:", parsed.scheme or "UNKNOWN")
