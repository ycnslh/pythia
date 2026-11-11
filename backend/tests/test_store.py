from store import StateStore, state_key


def test_roundtrip(tmp_path):
    store = StateStore(str(tmp_path))
    store.save("k", {"a": [1, 2]})
    assert store.load("k") == {"a": [1, 2]}


def test_missing_key_returns_default(tmp_path):
    assert StateStore(str(tmp_path)).load("nope", default="d") == "d"


def test_corrupt_file_returns_default(tmp_path):
    store = StateStore(str(tmp_path))
    (tmp_path / "bad.json").write_text("{not json")
    assert store.load("bad", default=[]) == []


def test_empty_directory_disables_persistence():
    store = StateStore("")
    assert not store.enabled
    store.save("k", 1)  # silently ignored
    assert store.load("k", default="d") == "d"


def test_unwritable_directory_disables_persistence(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    store = StateStore(str(blocker / "sub"))  # cannot mkdir under a regular file
    assert not store.enabled


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    store = StateStore(str(tmp_path))
    store.save("k", {"v": 1})
    store.save("k", {"v": 2})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["k.json"]


def test_state_key_is_filesystem_safe_and_unique():
    a = state_key("source", "BBC World/News ../x")
    b = state_key("source", "BBC World News x")
    assert "/" not in a and ".." not in a
    assert a != b  # same slug, different names
