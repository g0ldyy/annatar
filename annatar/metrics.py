from functools import wraps

from prometheus_client import Histogram


def time(histogram: Histogram, **label_values):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            labels = {label: kwargs.get(arg_name) for label, arg_name in label_values.items()}
            with histogram.labels(**labels).time():
                return func(*args, **kwargs)

        return wrapper

    return decorator
