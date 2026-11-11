import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import rss_to_discord as rss


class RssBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path_patch = patch.object(rss, 'STATE_PATH', Path(self.temp.name) / 'seen.json')
        self.path_patch.start()
        self.addCleanup(self.path_patch.stop)
        self.summary_patch = patch.object(rss, 'write_summary')
        self.summary_patch.start()
        self.addCleanup(self.summary_patch.stop)
        self.now = datetime(2026, 11, 10, 12, tzinfo=timezone.utc)
        self.feed = {'name': 'Source A', 'url': 'https://example.org/rss'}
        self.state = rss.load_state()

    def item(self, key, hours=1):
        return {'id': key, 'title': f'Actualité {key}', 'link': f'https://example.org/{key}',
                'source': self.feed['name'], 'published': self.now - timedelta(hours=hours)}

    def test_rss_and_atom_dates_links_and_html(self):
        xml = b'''<rss version="2.0"><channel><item><guid>a</guid><title>A &amp; B</title>
        <link>https://example.org/a</link><pubDate>Tue, 10 Nov 2026 13:00:00 +0100</pubDate>
        </item></channel></rss>'''
        item = rss.parse_feed(xml, 'A')[0]
        self.assertEqual(item['published'], self.now)
        self.assertEqual(item['title'], 'A & B')
        atom = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>b</id><title>B</title>
        <link rel="self" href="https://example.org/feed"/><link rel="alternate" href="https://example.org/b"/>
        <updated>2026-11-10T12:00:00Z</updated></entry></feed>'''
        self.assertEqual(rss.parse_feed(atom, 'B')[0]['link'], 'https://example.org/b')
        with self.assertRaises(rss.FeedError):
            rss.parse_feed(b'<html>Temporarily unavailable</html>', 'A')

    def test_backlog_is_preserved_then_deduplicated(self):
        entries = [self.item(str(i), hours=i + 1) for i in range(3)]
        with patch.object(rss, 'discord_post') as post:
            self.assertEqual(rss.publish_entries(self.feed, entries, self.state, 'endpoint', self.now), 2)
            state = rss.load_state()
            self.assertEqual(len(state['feeds'][self.feed['url']]['seen']), 2)
            self.assertEqual(rss.publish_entries(self.feed, entries, state, 'endpoint', self.now), 1)
            self.assertEqual(rss.publish_entries(self.feed, entries, state, 'endpoint', self.now), 0)
            self.assertEqual(post.call_count, 3)

    def test_failed_post_is_not_recorded_as_sent(self):
        entries = [self.item('first', 2), self.item('second', 1)]
        with patch.object(rss, 'discord_post', side_effect=[None, rss.PublishError('temporary failure')]):
            with self.assertRaises(rss.PublishError):
                rss.publish_entries(self.feed, entries, self.state, 'endpoint', self.now)
        recorded = rss.load_state()['feeds'][self.feed['url']]['seen']
        self.assertIn('first', recorded)
        self.assertNotIn('second', recorded)

    def test_each_source_gets_its_own_initial_history_baseline(self):
        with patch.object(rss, 'discord_post') as post:
            rss.publish_entries(self.feed, [self.item('new')], self.state, 'endpoint', self.now)
            second = {'name': 'Source B', 'url': 'https://example.org/second'}
            rss.publish_entries(second, [self.item('old', 72)], self.state, 'endpoint', self.now)
            self.assertEqual(post.call_count, 1)

    def test_future_items_wait_and_duplicate_guids_post_once(self):
        entries = [self.item('same'), self.item('same'), self.item('future', -1)]
        with patch.object(rss, 'discord_post') as post:
            rss.publish_entries(self.feed, entries, self.state, 'endpoint', self.now)
            self.assertEqual(post.call_count, 1)
            self.assertNotIn('future', rss.load_state()['feeds'][self.feed['url']]['seen'])

    def test_invalid_destination_is_rejected_without_revealing_secret(self):
        secret = 'private-token'
        with self.assertRaises(rss.PublishError) as ctx:
            rss.webhook_endpoint(f'https://example.org/api/webhooks/123/{secret}')
        self.assertNotIn(secret, str(ctx.exception))
        self.assertTrue(rss.webhook_endpoint('https://discord.com/api/webhooks/123/sample-token').endswith('?wait=true'))

    def test_all_sources_down_fail_instead_of_silent_success(self):
        with patch.object(rss, 'fetch_feed', side_effect=rss.FeedError('HTTP 503')), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rss.main(['--check']), 1)
        self.assertFalse(rss.STATE_PATH.exists())

    def test_dry_check_never_posts_or_modifies_state(self):
        with patch.object(rss, 'fetch_feed', return_value=[self.item('a')]), \
                patch.object(rss, 'discord_post') as post, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rss.main(['--check']), 0)
            post.assert_not_called()
        self.assertFalse(rss.STATE_PATH.exists())

    def test_same_article_across_feeds_with_tracking_posts_once(self):
        first=self.item('a'); second=self.item('b');second['link']=first['link']+'?utm_source=news'
        with patch.object(rss,'discord_post') as post:
            rss.publish_entries(self.feed,[first],self.state,'endpoint',self.now)
            rss.publish_entries({'name':'B','url':'https://example.org/b-rss'},[second],self.state,'endpoint',self.now)
            self.assertEqual(post.call_count,1)

    def test_daily_limit_keeps_unsent_items_pending(self):
        self.state['daily']={'date':self.now.date().isoformat(),'count':8}
        with patch.object(rss,'discord_post') as post:
            self.assertEqual(rss.publish_entries(self.feed,[self.item('a')],self.state,'endpoint',self.now),0)
            self.assertNotIn('a',self.state['feeds'][self.feed['url']]['seen'])
            self.assertEqual(rss.publish_entries(self.feed,[self.item('a')],self.state,'endpoint',self.now+timedelta(days=1)),1)
            self.assertEqual(post.call_count,1)

    def test_filters_and_stale_backlog(self):
        self.state['feeds'][self.feed['url']]={'initialized':True,'seen':{}}
        feed={**self.feed,'include_keywords':['inflation'],'exclude_keywords':['test']}
        good={**self.item('a'),'title':'Inflation outlook'}
        bad={**self.item('b'),'title':'Inflation test'}
        with patch.object(rss,'discord_post') as post:
            rss.publish_entries(feed,[good,bad,self.item('old',72)],self.state,'endpoint',self.now)
            self.assertEqual(post.call_count,1)

    def test_paris_time_is_used(self):
        self.assertIn('12:00',rss.format_message(self.item('a')))
        self.assertIn('heure de Paris',rss.format_message(self.item('a')))


if __name__ == '__main__':
    unittest.main()
