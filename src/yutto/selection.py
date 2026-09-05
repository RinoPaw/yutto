"""Selection expression parser.

Grammar::

    selection := item ("," item)* EOF
    item      := position | position? "~" position?
    position  := INTEGER | "^" | "$"

Whitespace is ignored between tokens. Ranges are inclusive and follow their
written direction. ``^`` denotes the first item, ``$`` the last item, and
negative integers are resolved from the end. Evaluation preserves expression
order and duplicate occurrences.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import NoReturn, TypeAlias

from yutto.exceptions import WrongArgumentError


class _TokenKind(Enum):
    INTEGER = auto()
    FIRST = auto()
    LAST = auto()
    RANGE = auto()
    COMMA = auto()
    EOF = auto()


@dataclass(frozen=True, slots=True)
class _Token:
    kind: _TokenKind
    lexeme: str
    offset: int


@dataclass(frozen=True, slots=True)
class Index:
    value: int


class Anchor(Enum):
    FIRST = "^"
    LAST = "$"


Position: TypeAlias = Index | Anchor


@dataclass(frozen=True, slots=True)
class Range:
    start: Position | None
    end: Position | None


SelectionItem: TypeAlias = Position | Range


@dataclass(frozen=True, slots=True)
class Selection:
    items: tuple[SelectionItem, ...]

    def resolve(self, total: int) -> tuple[int, ...]:
        if total < 0:
            raise ValueError("total must not be negative")
        if total == 0:
            raise WrongArgumentError("没有可供选择的项目")

        result: list[int] = []
        for item in self.items:
            if isinstance(item, Range):
                start = 1 if item.start is None else _resolve_position(item.start, total)
                end = total if item.end is None else _resolve_position(item.end, total)
                step = 1 if end >= start else -1
                result.extend(range(start, end + step, step))
            else:
                result.append(_resolve_position(item, total))
        return tuple(result)


def _resolve_position(position: Position, total: int) -> int:
    if position is Anchor.FIRST:
        value = 1
    elif position is Anchor.LAST:
        value = total
    else:
        value = position.value
        if value == 0:
            raise WrongArgumentError("不可使用 0 作为序号（序号从 1 开始计算）")
        if value < 0:
            value = total + value + 1

    if value < 1 or value > total:
        raise WrongArgumentError(f"序号 {value} 超出范围（1~{total}）")
    return value


class _Lexer:
    def __init__(self, source: str) -> None:
        self.source = source
        self.cursor = 0

    def scan(self) -> tuple[_Token, ...]:
        tokens: list[_Token] = []
        while self.cursor < len(self.source):
            char = self.source[self.cursor]
            if char.isspace():
                self.cursor += 1
                continue
            if char == "^":
                tokens.append(self._single(_TokenKind.FIRST))
                continue
            if char == "$":
                tokens.append(self._single(_TokenKind.LAST))
                continue
            if char == "~":
                tokens.append(self._single(_TokenKind.RANGE))
                continue
            if char == ",":
                tokens.append(self._single(_TokenKind.COMMA))
                continue
            if char == "-" or _is_ascii_digit(char):
                tokens.append(self._integer())
                continue
            self._error(self.cursor, f"无法识别字符 {char!r}")

        tokens.append(_Token(_TokenKind.EOF, "", len(self.source)))
        return tuple(tokens)

    def _single(self, kind: _TokenKind) -> _Token:
        offset = self.cursor
        lexeme = self.source[self.cursor]
        self.cursor += 1
        return _Token(kind, lexeme, offset)

    def _integer(self) -> _Token:
        start = self.cursor
        if self.source[self.cursor] == "-":
            self.cursor += 1
            if self.cursor >= len(self.source) or not _is_ascii_digit(self.source[self.cursor]):
                self._error(start, "负号后必须跟整数")

        digit_start = self.cursor
        while self.cursor < len(self.source) and _is_ascii_digit(self.source[self.cursor]):
            self.cursor += 1

        digits = self.source[digit_start:self.cursor]
        if len(digits) > 1 and digits.startswith("0"):
            self._error(digit_start, "整数不能包含前导零")

        return _Token(_TokenKind.INTEGER, self.source[start:self.cursor], start)

    def _error(self, offset: int, message: str) -> NoReturn:
        raise _selection_syntax_error(self.source, offset, message)


class _Parser:
    _POSITION_TOKENS = {_TokenKind.INTEGER, _TokenKind.FIRST, _TokenKind.LAST}

    def __init__(self, source: str, tokens: tuple[_Token, ...]) -> None:
        self.source = source
        self.tokens = tokens
        self.cursor = 0

    def parse(self) -> Selection:
        if self._peek().kind is _TokenKind.EOF:
            raise WrongArgumentError("选集参数不能为空")

        items = [self._item()]
        while self._match(_TokenKind.COMMA):
            if self._peek().kind in {_TokenKind.COMMA, _TokenKind.EOF}:
                self._error(self._peek(), "逗号后缺少选集项")
            items.append(self._item())

        if self._peek().kind is not _TokenKind.EOF:
            self._error(self._peek(), "选集项之间必须使用逗号分隔")
        return Selection(tuple(items))

    def _item(self) -> SelectionItem:
        if self._match(_TokenKind.RANGE):
            return Range(start=None, end=self._optional_position())

        start = self._position()
        if self._match(_TokenKind.RANGE):
            return Range(start=start, end=self._optional_position())
        return start

    def _optional_position(self) -> Position | None:
        if self._peek().kind in self._POSITION_TOKENS:
            return self._position()
        return None

    def _position(self) -> Position:
        token = self._peek()
        if self._match(_TokenKind.INTEGER):
            return Index(int(token.lexeme))
        if self._match(_TokenKind.FIRST):
            return Anchor.FIRST
        if self._match(_TokenKind.LAST):
            return Anchor.LAST
        self._error(token, "此处需要序号、^ 或 $")

    def _match(self, kind: _TokenKind) -> bool:
        if self._peek().kind is not kind:
            return False
        self.cursor += 1
        return True

    def _peek(self) -> _Token:
        return self.tokens[self.cursor]

    def _error(self, token: _Token, message: str) -> NoReturn:
        raise _selection_syntax_error(self.source, token.offset, message)


def _is_ascii_digit(char: str) -> bool:
    return "0" <= char <= "9"


def _selection_syntax_error(source: str, offset: int, message: str) -> WrongArgumentError:
    location = "末尾" if offset >= len(source) else f"第 {offset + 1} 个字符"
    return WrongArgumentError(f"选集参数（{source}）在{location}附近格式不正确：{message}")


def parse_selection(source: str) -> Selection:
    lexer = _Lexer(source)
    return _Parser(source, lexer.scan()).parse()


def compile_selection(source: str, total: int) -> tuple[int, ...]:
    """Parse a selection expression, then resolve it against a known 1-based context size."""
    return parse_selection(source).resolve(total)


__all__ = ["Anchor", "Index", "Range", "Selection", "compile_selection", "parse_selection"]
