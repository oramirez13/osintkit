"""Collection modules: scrape, domain, crawl, search, detect."""

from .base import BaseModule, BaseModuleConfig
from .crawl import crawl, CrawlConfig, CrawlResult
from .domain import analyze_domain, DomainReport
from .scrape import scrape_url, ScrapeSpec, FieldSpec
from .search import run_search, SearchResult, Hit
from .detect import detect_type, build_query, Query

__all__ = [
    "BaseModule",
    "BaseModuleConfig",
    "crawl",
    "CrawlConfig",
    "CrawlResult",
    "analyze_domain",
    "DomainReport",
    "scrape_url",
    "ScrapeSpec",
    "FieldSpec",
    "run_search",
    "SearchResult",
    "Hit",
    "detect_type",
    "build_query",
    "Query",
]
