from unittest.mock import patch

from static import find_static_dir, render_index


def test_find_static_dir_honours_setting(tmp_path):
    (tmp_path / "index.html").write_text("x")
    with patch("static.settings") as settings:
        settings.static_dir = str(tmp_path)
        assert find_static_dir() == tmp_path


def test_find_static_dir_ignores_directory_without_index(tmp_path):
    with patch("static.settings") as settings:
        settings.static_dir = str(tmp_path)
        found = find_static_dir()
    assert found != tmp_path


def test_render_index_without_head_still_injects():
    html = render_index("<div>app</div>")
    assert html.startswith("<script>window.__PYTHIA__=")
