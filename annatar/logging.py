import asyncio
import inspect
import logging
import os
import sys
from datetime import datetime
from functools import wraps
from typing import Any, Callable, TypeVar

import __main__
import structlog

log_level: str = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.getLevelName(log_level.upper()),
)

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def add_code_info(logger: logging.Logger, method_name: str, event_dict: Any) -> dict[str, Any]:
    frame = inspect.currentframe().f_back.f_back.f_back.f_back.f_back  # type: ignore
    event_dict["code_func"] = frame.f_code.co_name  # type: ignore
    fname: str = frame.f_code.co_filename.replace(root_dir, "").lstrip("/")  # type: ignore
    event_dict["code_line"] = frame.f_lineno  # type: ignore
    # event_dict["code_file"] = f"{fname}:{frame.f_lineno}"  # type: ignore
    return event_dict


structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        add_code_info,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.EventRenamer(to="msg"),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)


def init():
    # the work is done on load
    return None


# Define a generic return type
R = TypeVar("R")


def timestamped(func: Callable[..., R]) -> Any:
    # execution_time code_line=66 duration="0.459s" logger="annatar.logging" code_func="async_wrapper" function="annatar.debrid.pm:get_stream_links" request_id="3bdf27b5-4e8f-46f7-ab73-fbae2881d832"
    remove_keys: list[str] = [
        "logger",
        "code_func",
        "code_line",
        "function",
        "duration",
    ]
    if asyncio.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> R:
            start_time = datetime.now()
            result: R = await func(*args, **kwargs)
            end_time = datetime.now()
            structlog.get_logger().try_unbind(remove_keys).info(
                "execution_time",
                function=f"{func.__module__}:{func.__name__}",
                duration=f"{(end_time - start_time).total_seconds():.3f}s",
            )
            return result

        return async_wrapper
    else:

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> R:
            start_time = datetime.now()
            result: R = func(*args, **kwargs)
            end_time = datetime.now()
            structlog.get_logger().try_unbind(remove_keys).info(
                "execution_time",
                function=f"{func.__module__}:{func.__name__}",
                duration=f"{(end_time - start_time).total_seconds():.3f}s",
            )
            return result

        return wrapper
