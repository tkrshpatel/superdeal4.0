"""Verify the delay and its use by every production Playwright entry point."""
import sys
from types import ModuleType, SimpleNamespace

import pytest

from superdeal import browser_enrichment, browser_pacing
import image_enrichment
import pre_llm_research


@pytest.mark.parametrize("delay", [1.0, 1.37, 2.0])
def test_pause_uses_random_one_to_two_second_delay(monkeypatch, delay):
    calls = []
    def uniform(low, high):
        assert (low, high) == (1.0, 2.0)
        calls.append("random")
        return delay
    monkeypatch.setattr(browser_pacing.random, "uniform", uniform)
    monkeypatch.setattr(browser_pacing.time, "sleep", lambda seconds: calls.append(seconds))
    browser_pacing.pause_before_navigation()
    browser_pacing.pause_before_navigation()
    assert calls == ["random", delay, "random", delay]


@pytest.mark.parametrize("entry", ["metadata", "research", "image"])
def test_each_navigation_is_delayed_even_after_failure(monkeypatch, entry):
    events = []
    class Page:
        def set_default_timeout(self, value):
            pass
        def goto(self, url, **kwargs):
            events.append(("goto", url))
            raise RuntimeError("simulated navigation failure")
    class Context:
        def new_page(self):
            return Page()
        def route(self, *args):
            pass
        def close(self):
            pass
    class Browser:
        def new_context(self, **kwargs):
            return Context()
        def close(self):
            pass
    class Playwright:
        chromium = SimpleNamespace(launch=lambda **kwargs: Browser())
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    api = ModuleType("playwright.sync_api")
    api.sync_playwright = Playwright
    package = ModuleType("playwright")
    package.sync_api = api
    monkeypatch.setitem(sys.modules, "playwright", package)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)
    monkeypatch.setattr(browser_pacing.random, "uniform", lambda low, high: 1.5)
    monkeypatch.setattr(browser_pacing.time, "sleep", lambda delay: events.append(("pause", delay)))
    links = ["https://amazon.in/dp/one", "https://flipkart.com/two"]
    if entry == "metadata":
        for link in links:
            with pytest.raises(RuntimeError, match="simulated"):
                browser_enrichment.fetch_browser_metadata(link)
    elif entry == "research":
        result = pre_llm_research.research_message("\n".join(links), browser=Browser())
        assert all(item["status"].startswith("BROWSER_") for item in result.values())
    else:
        result = image_enrichment.scrape_image(links, browser=Browser(), detailed=True)
        assert result["reason"].startswith("BROWSER_")
    assert events == [("pause", 1.5), ("goto", links[0]),
                      ("pause", 1.5), ("goto", links[1])]


@pytest.mark.parametrize("entry", ["research", "image"])
def test_unsafe_links_do_not_wait_or_navigate(monkeypatch, entry):
    def fail(*args, **kwargs):
        raise AssertionError("Unsafe links must not start browser navigation")
    context = SimpleNamespace(route=lambda *args: None, close=lambda: None,
        new_page=lambda: SimpleNamespace(set_default_timeout=lambda value: None, goto=fail))
    browser = SimpleNamespace(new_context=lambda **kwargs: context)
    module = pre_llm_research if entry == "research" else image_enrichment
    monkeypatch.setattr(module, "pause_before_navigation", fail)
    if entry == "research":
        result = module.research_message("https://localhost/blocked", browser=browser)
        assert result["https://localhost/blocked"]["status"] == "UNSAFE_URL"
    else:
        # The implementation imports Playwright even when a browser is supplied.
        pytest.importorskip("playwright.sync_api")
        assert module.scrape_image(["https://localhost/blocked"], browser=browser) is None
