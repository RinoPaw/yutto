from __future__ import annotations

import re

from yutto.exceptions import WrongArgumentError

_NUMBER = re.compile(r"-?(?:0|[1-9]\d*)\Z")


def compile_selection(selection: str, total: int) -> tuple[int, ...]:
    """Compile a -p selection expression into 1-based indexes for a known context size."""
    if total < 0:
        raise ValueError("total must not be negative")

    selection = selection.strip()
    if not selection:
        raise WrongArgumentError("选集参数不能为空")
    if total == 0:
        return ()

    def resolve(token: str, default: int) -> int:
        if not token:
            return default
        if token == "^":
            return 1
        if token == "$":
            return total
        if not _NUMBER.fullmatch(token):
            raise WrongArgumentError(f"选集参数（{selection}）格式不正确")

        value = int(token)
        if value == 0:
            raise WrongArgumentError("不可使用 0 作为序号（序号从 1 开始计算）")
        return value if value > 0 else total + value + 1

    selected: set[int] = set()
    for part in selection.split(","):
        if not part or part.count("~") > 1:
            raise WrongArgumentError(f"选集参数（{selection}）格式不正确")

        if "~" in part:
            start_token, end_token = part.split("~")
            start = resolve(start_token, 1)
            end = resolve(end_token, total)
            if end < start:
                raise WrongArgumentError(f"终点值（{end}）应不小于起点值（{start}）")
            indexes = range(start, end + 1)
        else:
            indexes = (resolve(part, 1),)

        for index in indexes:
            if index < 1 or index > total:
                raise WrongArgumentError(f"序号 {index} 超出范围（1~{total}）")
            selected.add(index)

    return tuple(sorted(selected))
