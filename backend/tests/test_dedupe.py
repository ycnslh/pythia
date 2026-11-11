from dedupe import WINDOW_S, TitleDeduplicator
from store import StateStore


def test_first_title_is_not_duplicate():
    assert TitleDeduplicator().check_and_add("Earthquake strikes northern Japan") is False


def test_exact_repeat_is_duplicate():
    d = TitleDeduplicator()
    d.check_and_add("Earthquake strikes northern Japan")
    assert d.check_and_add("Earthquake strikes northern Japan") is True


def test_reworded_headline_from_another_outlet_is_duplicate():
    d = TitleDeduplicator()
    d.check_and_add("Strong earthquake strikes northern Japan, tsunami warning issued")
    assert d.check_and_add("Earthquake strikes northern Japan, tsunami warning issued") is True


def test_different_stories_are_kept():
    d = TitleDeduplicator()
    d.check_and_add("Earthquake strikes northern Japan")
    assert d.check_and_add("Central bank raises interest rates again") is False


def test_short_titles_only_match_when_identical():
    d = TitleDeduplicator()
    d.check_and_add("API is DOWN")
    assert d.check_and_add("DB is DOWN") is False


def test_titles_expire_after_the_window():
    d = TitleDeduplicator()
    d.check_and_add("Earthquake strikes northern Japan", now=0)
    assert d.check_and_add("Earthquake strikes northern Japan", now=WINDOW_S + 1) is False


def test_memory_survives_restart(tmp_path):
    store = StateStore(str(tmp_path))
    TitleDeduplicator(store).check_and_add("Earthquake strikes northern Japan")

    reloaded = TitleDeduplicator(StateStore(str(tmp_path)))
    assert reloaded.check_and_add("Earthquake strikes northern Japan") is True
