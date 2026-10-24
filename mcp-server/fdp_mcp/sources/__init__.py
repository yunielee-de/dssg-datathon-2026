"""Adapters for candidate new sources. Each module exposes NAME, HOMEPAGE, fetch() and to_mapped()."""

from fdp_mcp.sources import beratungsfinder

SOURCES = {beratungsfinder.NAME: beratungsfinder}
