import logging
import utils

logger = logging.getLogger("justyse.db")
logger.addHandler(utils.console_handler("Database"))
