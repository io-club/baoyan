from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    database_url: str
    rabbitmq_url: str
    admin_password: str
    log_dir: str
    work_dir: str
    poll_seconds: float
    default_timezone: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.getenv(
                "TASK_DATABASE_URL",
                "postgresql://baoyan:baoyan@postgres:5432/baoyan",
            ),
            rabbitmq_url=os.getenv(
                "TASK_RABBITMQ_URL",
                "amqp://baoyan:baoyan@rabbitmq:5672/%2F",
            ),
            admin_password=os.getenv("TASK_ADMIN_PASSWORD", "password"),
            log_dir=os.getenv("TASK_LOG_DIR", "/logs"),
            work_dir=os.getenv("TASK_WORK_DIR", "/workspace"),
            poll_seconds=float(os.getenv("TASK_POLL_SECONDS", "3")),
            default_timezone=os.getenv("TASK_DEFAULT_TIMEZONE", "Asia/Taipei"),
        )


settings = Settings.from_env()


def current_admin_password() -> str:
    """Use the same Nacos credential as the platform; retain the last valid config on outages."""
    import time
    import urllib.request
    import urllib.parse
    import yaml
    cached = getattr(current_admin_password, '_cache', None)
    if cached and time.monotonic()-cached[0] < 3:
        return cached[1]
    try:
        query=urllib.parse.urlencode({'dataId':'baoyan-platform.yaml','group':'BAOYAN_GROUP'})
        url=os.getenv('NACOS_URL','http://nacos:8848/nacos').rstrip('/')+'/v1/cs/configs?'+query
        with urllib.request.urlopen(url,timeout=3) as r:
            document=yaml.safe_load(r.read()) or {}
        password=str(document['baoyan']['application']['admin-password'])
        current_admin_password._cache=(time.monotonic(),password)
        return password
    except Exception:
        return cached[1] if cached else settings.admin_password

