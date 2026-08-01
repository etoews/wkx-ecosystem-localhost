"""Collectors: pure functions from ``Machine`` probe results to typed models.

A Collector never touches subprocess or the filesystem directly; it reaches the
host only through the ``Machine`` seam and returns a model the API serialises
verbatim.
"""
