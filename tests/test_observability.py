import logging

from camera_tracker.observability import configure_worker_logging


def test_worker_logging_writes_local_utf8_log_file(tmp_path) -> None:
    path = tmp_path / "tracker.log"
    logger = configure_worker_logging(path)
    logger.info("test event")
    for handler in logger.handlers:
        handler.flush()

    assert "test event" in path.read_text(encoding="utf-8")
    for handler in list(logger.handlers):
        if isinstance(handler, logging.FileHandler) and handler.baseFilename == str(path.resolve()):
            logger.removeHandler(handler)
            handler.close()
