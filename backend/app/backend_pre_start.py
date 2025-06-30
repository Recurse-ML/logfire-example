import logfire
import logging

from sqlalchemy import Engine
from sqlmodel import Session, select
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed

from app.core.db import engine
from app.core.logfire_config import configure_logfire

# Configure logfire
configure_logfire()

max_tries = 60 * 5  # 5 minutes
wait_seconds = 1

logger = logging.getLogger("logfire")

@retry(
    stop=stop_after_attempt(max_tries),
    wait=wait_fixed(wait_seconds),
    before=before_log(logfire, "INFO"),
    after=after_log(logfire, "WARNING"),
)
def init(db_engine: Engine) -> None:
    try:
        with Session(db_engine) as session:
            # Try to create session to check if DB is awake
            session.exec(select(1))
    except Exception as e:
        logfire.error(e)
        raise e


def main() -> None:
    logfire.info("Initializing service")
    init(engine)
    logfire.info("Service finished initializing")


if __name__ == "__main__":
    main()
