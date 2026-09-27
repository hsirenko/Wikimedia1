"""The Markdown subset -> HTML converter used for report.html."""

from wiki_market_intel.reporting.html import markdown_to_html, page


def test_tables_keep_alignment_and_escape_text():
    html = markdown_to_html("| Edition | Views |\n|---|---:|\n| de.wikipedia | 56,910 <b> |\n")
    assert '<th class="num">Views</th>' in html and '<td class="num">56,910 &lt;b&gt;</td>' in html
    assert "<td>de.wikipedia</td>" in html


def test_inline_marks_and_code():
    html = markdown_to_html("A **bold** word, _an aside_, and `pageviews_meditation_de.json`.")
    assert "<strong>bold</strong>" in html and "<em>an aside</em>" in html
    assert "<code>pageviews_meditation_de.json</code>" in html        # underscores in code are left alone


def test_snake_case_is_not_italic():
    assert "<em>" not in markdown_to_html("See signals.growth_basis and topic_share for details.")


def test_blocks():
    html = markdown_to_html("# Title\n\n_meta line_\n\n- one\n- two\n\n> a note\n\nplain\ntext\n")
    assert "<h1>Title</h1>" in html and '<p class="meta">meta line</p>' in html
    assert "<ul><li>one</li><li>two</li></ul>" in html and "<blockquote>a note</blockquote>" in html
    assert "<p>plain text</p>" in html


def test_page_embeds_images_and_supports_dark_mode(tmp_path):
    (tmp_path / "charts").mkdir()
    (tmp_path / "charts" / "c.png").write_bytes(b"\x89PNG fake")
    doc = page("# Report\n\n![Chart](charts/c.png)\n", tmp_path, lang="uk")
    assert '<html lang="uk">' in doc and "<title>Report</title>" in doc
    assert 'src="data:image/png;base64,' in doc
    assert "prefers-color-scheme: dark" in doc


def test_missing_image_keeps_its_path(tmp_path):
    assert 'src="charts/none.png"' in page("![x](charts/none.png)", tmp_path)
