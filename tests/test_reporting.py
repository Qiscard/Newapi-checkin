import unittest

from models import CheckinResult
from reporting import build_report_html, build_report_markdown, build_report_text


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.results = [CheckinResult(
            name='<Admin>|primary',
            success=False,
            message='<script>alert(1)</script> | expired',
            session_expired=True,
        )]

    def test_html_report_escapes_untrusted_values(self):
        report = build_report_html(self.results, '2026-07-14 <now>')

        self.assertNotIn('<script>alert(1)</script>', report)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', report)
        self.assertIn('&lt;Admin&gt;|primary', report)
        self.assertIn('2026-07-14 &lt;now&gt;', report)

    def test_markdown_report_escapes_html_and_table_delimiters(self):
        report = build_report_markdown(self.results, '2026-07-14')

        self.assertNotIn('<script>', report)
        self.assertIn('&lt;script&gt;', report)
        self.assertIn('\\|primary', report)
        self.assertIn('\\| expired', report)

    def test_text_report_flattens_newlines(self):
        result = CheckinResult(name='name\nnext', success=True, message='ok\nnext')
        report = build_report_text([result], '2026-07-14')

        self.assertIn('name next', report)
        self.assertIn('ok next', report)


if __name__ == '__main__':
    unittest.main()
