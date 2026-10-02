"""Synthetic fixtures only. No real API calls or mail delivery."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError

from src.research import ROOT, SKILLS, analysis_brief, brand_domain, collect, plan, video_url, view_sample
from src.research_client import BudgetExceeded, NoRedirect, ResearchClient, ResearchError

VIDEO = 'https://www.youtube.com/watch?v=abcdefghijk'
OTHER = 'https://www.youtube.com/watch?v=lmnopqrstuv'


class ResearchTests(unittest.TestCase):
    def client(self, folder, data, credits=10, clock=lambda: 100):
        calls = []
        def opener(request, timeout):
            calls.append(request.full_url)
            value = data(request.full_url) if callable(data) else data
            return io.StringIO(json.dumps(value))
        client = ResearchClient(credits, folder, opener=opener, api_key='synthetic-test-key', clock=clock)
        return client, calls

    def test_zero_allowance_no_request(self):
        with tempfile.TemporaryDirectory() as folder:
            client, calls = self.client(folder, {'success': True}, 0)
            with self.assertRaises(BudgetExceeded): client.get('/v1/youtube/channel', {'handle': 'test'})
            self.assertEqual(calls, [])

    def test_cache_reused_without_key_or_allowance(self):
        with tempfile.TemporaryDirectory() as folder:
            client, calls = self.client(folder, {'success': True, 'name': 'Synthetic'})
            first = client.get('/v1/youtube/channel', {'handle': 'test'})
            second = ResearchClient(0, folder, clock=lambda: 110)
            self.assertEqual(second.get('/v1/youtube/channel', {'handle': 'test'}), first)
            self.assertEqual(len(calls), 1)
            self.assertEqual(second.usage()['cache_hits'], 1)
            self.assertEqual(second.usage()['actual_credits'], 0)

    def test_expired_cache_cannot_spend_without_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            client, _ = self.client(folder, {'success': True})
            client.get('/v1/youtube/channel', {'handle': 'test'})
            later = ResearchClient(0, folder, clock=lambda: 100000)
            with self.assertRaises(BudgetExceeded): later.get('/v1/youtube/channel', {'handle': 'test'})

    def test_budget_counts_failed_attempts_no_retry_or_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            client, calls = self.client(folder, {'success': False}, 1)
            with self.assertRaises(ResearchError): client.get('/v1/youtube/channel', {'handle': 'test'})
            with self.assertRaises(BudgetExceeded): client.get('/v1/youtube/channel', {'handle': 'test'})
            self.assertEqual(len(calls), 1)
            self.assertEqual(list(Path(folder).glob('*.json')), [])

    def test_unsupported_endpoint_and_ai_fallback_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            client, calls = self.client(folder, {'success': True})
            with self.assertRaises(ResearchError): client.get('/v1/detect/age-gender', {})
            with self.assertRaises(ResearchError): client.get('/v1/youtube/video/transcript', {'url': VIDEO, 'use_ai_as_fallback': True})
            self.assertEqual(calls, [])

    def test_http_errors_do_not_expose_response_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            def fail(request, timeout):
                raise HTTPError(request.full_url, 401, 'secret-test-value', {}, io.StringIO('secret-test-value'))
            client = ResearchClient(1, folder, opener=fail, api_key='synthetic-test-key')
            with self.assertRaises(ResearchError) as ctx: client.get('/v1/youtube/channel', {'handle': 'test'})
            self.assertNotIn('secret-test-value', str(ctx.exception))
            self.assertIn('401', str(ctx.exception))

    def test_redirect_refused_before_following(self):
        with self.assertRaises(ResearchError):
            NoRedirect().redirect_request(None, None, 302, '', {}, 'https://outside.example/')

    def test_unexpected_provider_charge_stops_next_request(self):
        with tempfile.TemporaryDirectory() as folder:
            client, calls = self.client(folder, {'success': True, 'credits_charged': 2})
            with self.assertRaises(ResearchError): client.get('/v1/youtube/channel', {'handle': 'test'})
            with self.assertRaises(BudgetExceeded): client.get('/v1/youtube/channel', {'handle': 'other'})
            self.assertEqual(len(calls), 1)

    def test_plans_are_bounded_and_include_all_requested_skills(self):
        spec = plan('sponsors', ['test', 'test'], 5, [VIDEO, VIDEO], ['comment-mining'])
        self.assertEqual(spec['max_requests'], 14)
        self.assertEqual(spec['traversal_depth'], 1)
        self.assertIn('comment-mining', spec['skills'])
        with self.assertRaises(ValueError): plan('sponsors', ['test'], 11)
        with self.assertRaises(ValueError): plan('creator', ['test'], related_urls=[VIDEO])

    def test_video_and_domain_normalization(self):
        self.assertEqual(video_url('https://youtu.be/abcdefghijk?si=ignored'), VIDEO)
        self.assertEqual(brand_domain('https://www.Example.com/promo?a=1'), 'example.com')
        with self.assertRaises(ValueError): video_url('https://youtube.com.evil.example/watch?v=abcdefghijk')
        self.assertIsNone(brand_domain('https://name:secret@example.com'))

    def test_median_does_not_become_thirty_day_forecast(self):
        sample = view_sample([{'viewCountInt': n} for n in [100, 200, 9000, True, None, -1, float('nan')]])
        self.assertEqual(sample['median_views'], 200)
        self.assertEqual(sample['count'], 3)
        self.assertIn('Not a 30 day forecast', sample['basis'])

    def test_partial_budget_preserves_known_evidence(self):
        def responses(url):
            if 'channel-videos' in url: return {'success': True, 'videos': [{'url': VIDEO, 'viewCountInt': 100}]}
            return {'success': True, 'channelId': 'synthetic-channel', 'country': 'US'}
        with tempfile.TemporaryDirectory() as folder:
            client, calls = self.client(folder, responses, 2)
            result = collect(plan('creator', ['test']), client)
            self.assertFalse(result['complete'])
            self.assertEqual(len(calls), 2)
            self.assertEqual(result['creators'][0]['audience_demographics'], 'Pending, request channel analytics')
            self.assertTrue(result['issues'])

    def test_missing_captions_remain_unavailable(self):
        def responses(url):
            if 'channel-videos' in url: return {'success': True, 'videos': [{'url': VIDEO}]}
            return {'success': True}
        with tempfile.TemporaryDirectory() as folder:
            client, _ = self.client(folder, responses)
            result = collect(plan('creator', ['test']), client)
            self.assertEqual(result['creators'][0]['latest_transcript']['status'], 'Unavailable')

    def test_sponsors_deduped_excluded_and_never_auto_confirmed(self):
        def responses(url):
            if 'channel-videos' in url: return {'success': True, 'videos': [{'url': VIDEO}]}
            if '/sponsors?' in url:
                return {'success': True, 'video': {'isPaidPromotion': True}, 'suspectedSponsors': [
                    {'name': 'Synthetic Brand', 'website': 'www.example.com', 'confidence': 'high', 'evidence': [{'text': 'Synthetic sponsor segment'}]},
                    {'name': 'Excluded', 'website': 'already.example'}]}
            return {'success': True, 'publishedTime': '2026-09-01'}
        with tempfile.TemporaryDirectory() as folder:
            client, calls = self.client(folder, responses)
            result = collect(plan('sponsors', ['test'], 1, [VIDEO, OTHER]), client, ['https://already.example'])
            self.assertEqual(len(calls), 6) # Same video encountered again is not fetched twice.
            self.assertEqual(len(result['sponsor_candidates']), 1)
            item = result['sponsor_candidates'][0]
            self.assertFalse(item['confirmed_sponsorship'])
            self.assertEqual(len(item['evidence']), 2)
            self.assertEqual(item['evidence'][1]['discovery']['kind'], 'observed_related_video')

    def test_changed_plan_rejected_before_collection(self):
        spec = plan('creator', ['test'])
        spec['max_reserved_credits'] = 10000
        with self.assertRaises(ValueError): collect(spec, None)

    def test_all_thirteen_playbooks_available_with_guardrails(self):
        self.assertEqual(len(SKILLS), 13)
        for name in SKILLS:
            path = ROOT / 'vendor' / 'scrapecreators' / 'skills' / name / 'SKILL.md'
            self.assertTrue(path.is_file())
            self.assertIn('name: ' + name, path.read_text())
        brief = analysis_brief({'complete': False, 'creators': []}, list(SKILLS))
        self.assertEqual(len(brief['instructions']), 13)
        self.assertTrue(brief['approval_required'])
        self.assertIn('Never send or approve', ' '.join(brief['rules']))


if __name__ == '__main__': unittest.main()
