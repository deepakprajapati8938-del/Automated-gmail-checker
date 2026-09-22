from app.email.parser import clean_body, html_to_text, strip_signature, trim_quoted_replies


def test_html_to_text_strips_script_and_style():
    html = "<html><head><style>.a{}</style></head><body><script>evil()</script><p>Hello</p></body></html>"
    text = html_to_text(html)
    assert "Hello" in text
    assert "evil" not in text
    assert "{}" not in text


def test_html_to_text_strips_tracking_pixel():
    html = '<div>Real content</div><img src="https://track.example.com/p.gif" width="1" height="1">'
    text = html_to_text(html)
    assert "Real content" in text


def test_trim_quoted_replies_keeps_head():
    text = "New message here.\n\nOn Tue, Sep 9, 2026, Alice wrote:\n> old stuff\n> more old stuff"
    trimmed = trim_quoted_replies(text, max_quote_levels=0)
    assert "New message here." in trimmed


def test_strip_signature_keeps_content_before_delimiter():
    text = "Please review the attached document.\n-- \nJohn Doe\nSenior Engineer"
    stripped = strip_signature(text)
    assert "Please review" in stripped
    assert "Senior Engineer" not in stripped


def test_strip_signature_no_delimiter_keeps_everything():
    text = "Just a plain message with no signature block."
    assert strip_signature(text) == text


def test_clean_body_prefers_plain_text_over_html():
    body = clean_body("Plain version", "<p>HTML version</p>")
    assert body == "Plain version"


def test_clean_body_falls_back_to_html():
    body = clean_body(None, "<p>Only HTML here</p>")
    assert "Only HTML here" in body
