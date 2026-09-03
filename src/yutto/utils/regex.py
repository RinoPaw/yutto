from __future__ import annotations

import re

_AV_ID = re.compile(r"av(?P<aid>[0-9]+)", re.IGNORECASE)
_BV_ID = re.compile(r"(?P<bvid>BV[A-Za-z0-9]+)", re.IGNORECASE)
_EP_ID = re.compile(r"ep(?P<episode_id>[0-9]+)", re.IGNORECASE)
_SS_ID = re.compile(r"ss(?P<season_id>[0-9]+)", re.IGNORECASE)
_MD_ID = re.compile(r"md(?P<media_id>[0-9]+)", re.IGNORECASE)
