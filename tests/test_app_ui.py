from app import app_ui


def test_app_includes_visible_run_progress_indicator():
    html = app_ui.get_html_string()

    assert 'id="run-progress"' in html
    assert "Processing is in progress" in html
    assert 'aria-live="polite"' in html
    assert '$(document).on("shiny:idle"' in html
