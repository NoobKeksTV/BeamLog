import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("wiki_sync", Path(__file__).parent.parent / "build_tools" / "wiki_sync.py")
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)


def test_links_lose_md_extension():
    src = "Siehe [Installation](Installation.md), [Port 80](Deploy.md#ohne-nginx-direkt-auf-port-80), [extern](https://x.de/a.md), ![Bild](img/a.png), [oben](#start)"
    assert ws.convert(src) == ("Siehe [Installation](Installation), [Port 80](Deploy#ohne-nginx-direkt-auf-port-80), [extern](https://x.de/a.md), "
                               f"![Bild]({ws.RAW}/img/a.png), [oben](#start)")
    assert ws.convert('<a href="x"><img src="img/v.jpg" width="9"></a>') == f'<a href="x"><img src="{ws.RAW}/img/v.jpg" width="9"></a>'


def test_sync_real_wiki(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "Alt.md").write_text("weg")
    ws.sync(Path(__file__).parent.parent / "docs" / "wiki", tmp_path)
    assert (tmp_path / "Home.md").exists() and (tmp_path / "img" / "loggen.png").exists() and (tmp_path / ".git").exists()
    assert not (tmp_path / "Alt.md").exists()
    side = (tmp_path / "_Sidebar.md").read_text(encoding="utf-8")
    assert "- [Installation](Installation)" in side and "(Fehlersuche)" in side
    assert ".md)" not in (tmp_path / "Home.md").read_text(encoding="utf-8")
