from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_cockpit_renders_without_api_key():
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=20).run()
    assert not app.exception
    assert len(app.metric) >= 6
    assert len(app.chat_message) >= 1
    assert len(app.button) >= 5
    assert any("추천 질문" in item.value for item in app.markdown)
