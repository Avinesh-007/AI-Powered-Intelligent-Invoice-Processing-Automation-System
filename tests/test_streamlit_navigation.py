from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).resolve().parent.parent / "frontend" / "app.py")


def test_streamlit_app_default_dashboard():
    """Verify default launch of the Streamlit application on Dashboard page."""
    at = AppTest.from_file(APP_PATH, default_timeout=20).run()
    assert not at.exception, f"App threw exceptions: {[e.value for e in at.exception]}"
    # Verify title is displayed
    assert any("Executive Dashboard" in str(title.value) for title in at.title)


def test_streamlit_app_navigation_pages():
    """Verify navigation to different sections of the redesigned application."""
    pages = [
        "📊 Dashboard",
        "🚀 Upload & Process",
        "📑 Invoice Registry",
        "🔍 Detailed Analysis",
        "⚖️ Approval Queue",
        "📈 Spend Analytics",
        "📥 Reports & Export",
        "📜 Audit Trail",
        "⚙️ System Health",
    ]

    at = AppTest.from_file(APP_PATH, default_timeout=20).run()
    assert not at.exception

    for page in pages:
        # Find the sidebar navigation radio
        if len(at.sidebar.radio) > 0:
            nav_radio = at.sidebar.radio[0]
            nav_radio.set_value(page).run(timeout=20)
            assert not at.exception, f"Exception while navigating to {page}: {[e.value for e in at.exception]}"
