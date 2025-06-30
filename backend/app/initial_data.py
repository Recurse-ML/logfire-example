import logfire

from sqlmodel import Session

from app.core.db import engine, init_db
from app.core.logfire_config import configure_logfire

# Configure logfire
configure_logfire()


def init() -> None:
    with Session(engine) as session:
        init_db(session)


def main() -> None:
    logfire.info("Creating initial data")
    init()
    logfire.info("Initial data created")


if __name__ == "__main__":
    main()
