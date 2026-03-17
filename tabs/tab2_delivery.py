"""Compatibility wrapper for tab2 delivery analysis."""

from tabs.tab2.views import render as _render


def render(ana_df, run_meta=None, cache_key=None):
    return _render(ana_df, run_meta=run_meta, cache_key=cache_key)
