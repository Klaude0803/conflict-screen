import unittest
from datetime import datetime, timezone
from src.outreach import next_send_time, prepare_outreach, research_latest
from src.conflict import screen_conflict, UNVERIFIED

class OutreachTests(unittest.TestCase):
    def test_recipient_local_window(self):
        now = datetime(2026, 10, 2, 2, tzinfo=timezone.utc)
        result = next_send_time('Asia/Almaty', now)
        self.assertEqual(result.strftime('%Y-%m-%d %H:%M'), '2026-10-06 09:03')
    def test_explicit_monday(self):
        result = next_send_time('America/Chicago', datetime(2026, 10, 1, tzinfo=timezone.utc), '2026-10-05 09:03')
        self.assertEqual(result.weekday(), 0)
    def test_dst_invalid(self):
        with self.assertRaises(ValueError):
            next_send_time('America/Chicago', datetime(2026, 1, 1, tzinfo=timezone.utc), '2026-03-08 02:30')
    def test_draft_hold_and_escape(self):
        result = prepare_outreach('creator@example.com', 'owner@example.com', 'Cloaked opportunity', '<script>test</script>', 'America/Chicago', 'Confirmed email', {'source_url':'https://example.com'}, now=datetime(2026, 10, 1, tzinfo=timezone.utc), sender_profiles={'owner@example.com':{'name':'Example Owner','signature_html':'Example Owner'}})
        self.assertEqual(result['queue']['Status'], 'Hold')
        self.assertEqual(result['queue']['Gmail Draft ID'], '')
        self.assertIn('&lt;script&gt;', result['draft']['html'])
        self.assertIn('Example Owner', result['draft']['html'])
    def test_partnerships_requires_signature(self):
        with self.assertRaises(ValueError):
            prepare_outreach('a@example.com', 'partnerships@example.com', 'Subject', 'Body', 'UTC', 'Confirmed', {'source_url':'https://example.com'})
    def test_missing_transcript_is_explicit(self):
        def fetch(path, params):
            if 'channel-videos' in path:
                return {'videos':[{'url':'https://www.youtube.com/watch?v=abc', 'title':'Title'}]}
            return {'transcript_only_text':None}
        self.assertEqual(research_latest('creator', fetch)['research_status'], 'Transcript unavailable')
    def test_mock_history_cannot_clear(self):
        self.assertEqual(screen_conflict({'verified':False, 'recent_sponsors':[{'name':'Squarespace','date':'2026-09-01'}]}, 'NordVPN')['status'], UNVERIFIED)

if __name__ == '__main__': unittest.main()
