from app.converters.html import html_to_markdown


def test_html_converter_preserves_nested_sharepoint_emphasis_and_links() -> None:
    _, markdown = html_to_markdown(
        b"""
        <p>Take place<strong>Wednesday, October 14, 2026</strong>, at campus.</p>
        <ul>
          <li>Sign up for<strong><a href="https://example.com/alerts"><strong>Wiki Alerts</strong></a></strong> (log in).</li>
          <li>Learn more about <a href="https://example.com/threat"><strong>responding to an active threat</strong></a>.</li>
          <li>Learn more about <a href="https://example.com/threat">r<strong>esponding to an active threat</strong></a>.</li>
        </ul>
        """
    )

    assert "Take place **Wednesday, October 14, 2026**, at campus." in markdown
    assert "- Sign up for **[Wiki Alerts](https://example.com/alerts)** (log in)." in markdown
    assert markdown.count(
      "- Learn more about [**responding to an active threat**](https://example.com/threat)."
    ) == 2