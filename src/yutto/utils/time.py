from __future__ import annotations

import time

TIME_FULL_FMT = "%Y-%m-%d %H:%M:%S"
TIME_DATE_FMT = "%Y-%m-%d"


def parse_local_timestamp(value: str) -> int:
    for fmt in (TIME_DATE_FMT, TIME_FULL_FMT):
        try:
            return int(time.mktime(time.strptime(value, fmt)))
        except ValueError:
            pass
    raise ValueError(f"无法解析时间 {value!r}，请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS")


def get_time_stamp_by_now() -> int:
    return int(time.time())


def get_time_str_by_now(fmt: str = TIME_FULL_FMT):
    time_stamp_now = time.time()
    return get_time_str_by_stamp(time_stamp_now, fmt)


def get_time_str_by_stamp(stamp: float, fmt: str = TIME_FULL_FMT):
    local_time = time.localtime(stamp)
    return time.strftime(fmt, local_time)


def get_time_struct_by_stamp(stamp: float):
    return time.localtime(stamp)
