"""Service-layer helpers shared by the routers (issue #3).

Routers stay thin; heavier work (artwork caching, import orchestration) lives
here. Currently: ``artwork`` — cover download + path-traversal-safe serving.
"""
