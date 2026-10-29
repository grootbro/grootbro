import contextlib
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

SCRIPT = Path(__file__).with_name('render-contributions.py')


def pr(number, repo, merged, title='Fix & improve [preview]'):
    return {'id': number, 'number': number, 'title': title,
            'repository_url': f'https://api.github.com/repos/{repo}',
            'html_url': f'https://github.com/{repo}/pull/{number}',
            'pull_request': {'merged_at': merged}}


class RendererTests(unittest.TestCase):
    def render(self, pages, recent=False):
        requests = []

        def fetch(request, timeout):
            requests.append(request.full_url)
            return io.StringIO(json.dumps(pages[len(requests) - 1]))

        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                Path('assets').mkdir()
                Path('assets/open-source-light.svg').write_text('last good card')
                Path('readme.md').write_text('Before\n<!-- merged-prs:start -->\nold\n<!-- merged-prs:end -->\nAfter')
                with patch.dict(os.environ, GITHUB_REPOSITORY_OWNER='grootbro', GH_TOKEN='test'), \
                     patch('urllib.request.urlopen', side_effect=fetch), \
                     contextlib.redirect_stdout(io.StringIO()):
                    try:
                        runpy.run_path(str(SCRIPT))
                    except RuntimeError as error:
                        return error, Path('assets/open-source-light.svg').read_text(), requests
                prefix = 'recent-' if recent else ''
                svgs = [Path(f'assets/open-source-{prefix}{theme}.svg').read_text() for theme in ('light', 'dark')]
                return svgs, Path('readme.md').read_text(), requests
            finally:
                os.chdir(previous)

    def test_all_projects_pages_latest_merge_and_clickable_history(self):
        old = pr(1, 'new/project', '2020-01-01T00:00:00Z')
        newer = pr(2, 'new/project', '2026-10-28T00:00:00Z')
        latest = pr(3, 'another/project', '2026-10-29T00:00:00Z')
        svgs, readme, requests = self.render([
            {'total_count': 3, 'items': [old, latest]},
            {'total_count': 3, 'items': [newer]},
        ])
        self.assertIn('page=2', requests[1])
        for svg in svgs:
            ET.fromstring(svg)
            self.assertIn('3 merged pull requests across 2 projects', svg)
            self.assertLess(svg.index('another/project'), svg.index('new/project'))
            self.assertIn('#2 · merged 28 Oct 2026', svg)
            self.assertNotIn('#1 · merged', svg)
        self.assertIn('https://github.com/new/project/pull/1', readme)
        self.assertIn('Fix &amp; improve \\[preview\\]', readme)
        self.assertTrue(readme.startswith('Before\n'))
        self.assertTrue(readme.endswith('\nAfter'))

    def test_recent_card_shows_five_prs_not_five_projects(self):
        items = [pr(n, 'same/project', f'2026-10-{n:02d}T00:00:00Z') for n in range(1, 7)]
        svgs, readme, _ = self.render([{'total_count': 6, 'items': items}], recent=True)
        for svg in svgs:
            ET.fromstring(svg)
            self.assertEqual(svg.count('>same/project</text>'), 5)
            self.assertIn('6 merged pull requests across 1 projects', svg)
            self.assertNotIn('#1 · merged', svg)
            self.assertLess(svg.index('#6 · merged'), svg.index('#5 · merged'))
        self.assertIn('<details>\n<summary><b>Explore all 1 projects', readme)
        self.assertIn('Browse all 6 merged pull requests', readme)
        self.assertEqual(readme.count('https://github.com/same/project/pull/'), 6)

    def test_rejects_incomplete_search(self):
        error, svg, _ = self.render([{'incomplete_results': True}])
        self.assertIn('incomplete', str(error))
        self.assertEqual(svg, 'last good card')

    def test_rejects_truncated_search(self):
        error, svg, _ = self.render([{'total_count': 1001, 'items': []}])
        self.assertIn('1000-result', str(error))
        self.assertEqual(svg, 'last good card')

    def test_rejects_duplicate_results(self):
        item = pr(1, 'new/project', '2026-10-28T00:00:00Z')
        error, svg, _ = self.render([{'total_count': 2, 'items': [item, item]}])
        self.assertIn('duplicate', str(error))
        self.assertEqual(svg, 'last good card')


if __name__ == '__main__':
    unittest.main()
