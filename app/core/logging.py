import logging
import sys


def configure_logging() -> None:
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="[%(asctime)s] | [%(levelname)s] | [%(name)s] | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
