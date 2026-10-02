"""Bounded public-data collection. No AI generation or mail delivery."""
import hashlib
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_ROOT = 'https://api.scrapecreators.com'
# Conservative reservation per attempt. Failed requests are not automatically retried.
ENDPOINTS = {
    '/v1/youtube/channel': {'handle', 'channelId', 'url', 'cache_max_age'},
    '/v1/youtube/channel-videos': {'handle', 'channelId', 'sort', 'continuationToken'},
    '/v1/youtube/video': {'url'},
    '/v1/youtube/video/transcript': {'url', 'language', 'cache_max_age'},
    '/v1/youtube/video/sponsors': {'url', 'language'},
    '/v1/youtube/search': {'query', 'type', 'uploadDate', 'sortBy', 'continuationToken'},
}


class ResearchError(ValueError):
    pass


class BudgetExceeded(ResearchError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ResearchError('Redirect refused. Credentials stay on the approved API host.')


def safe_open(request, timeout=30):
    return build_opener(NoRedirect()).open(request, timeout=timeout)


class ResearchClient:
    def __init__(self, approved_credits=0, cache_dir='.research-cache', ttl_seconds=86400,
                 opener=safe_open, clock=time.time, api_key=None):
        if type(approved_credits) is not int or approved_credits < 0:
            raise ValueError('Approved credits must be a nonnegative integer.')
        if ttl_seconds < 0:
            raise ValueError('Cache lifetime must be nonnegative.')
        self.approved_credits = approved_credits
        self.reserved_credits = 0
        self.actual_credits = 0
        self.cache_hits = 0
        self.cache_dir = Path(cache_dir)
        self.ttl = ttl_seconds
        self.opener = opener
        self.clock = clock
        self.api_key = api_key
        self.receipts = []

    def get(self, path, params):
        if path not in ENDPOINTS or set(params) - ENDPOINTS[path]:
            raise ResearchError('Unsupported endpoint or parameter. Validate current documentation first.')
        canonical = json.dumps([path, params], sort_keys=True, separators=(',', ':'))
        cache_path = self.cache_dir / (hashlib.sha256(canonical.encode()).hexdigest() + '.json')
        try:
            cached = json.loads(cache_path.read_text())
            if not isinstance(cached, dict) or not isinstance(cached.get('response'), dict):
                raise ValueError('Invalid cache')
            age = self.clock() - cached['fetched_at']
            if 0 <= age < self.ttl and cached['response'].get('success') is True:
                self.cache_hits += 1
                self.receipts.append({'endpoint': path, 'cache_hit': True,
                                      'fetched_at': cached['fetched_at'], 'reserved_credits': 0})
                return cached['response']
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if self.reserved_credits >= self.approved_credits:
            raise BudgetExceeded('Credit allowance exhausted. No further request made.')
        key = self.api_key or os.environ.get('SCRAPECREATORS_API_KEY') or os.environ.get('SCRAPE_CREATORS_API_KEY')
        if not key:
            raise ResearchError('Set the API key privately in the runtime. Never paste or commit it.')
        self.reserved_credits += 1
        req = Request(API_ROOT + path + '?' + urlencode(params), headers={'x-api-key': key})
        # Never surface response bodies, headers or credentials in errors.
        try:
            with self.opener(req, timeout=30) as response:
                if hasattr(response, 'geturl') and response.geturl() != req.full_url:
                    raise ResearchError('Unexpected redirect. Do not use the result.')
                result = json.load(response)
        except HTTPError as exc:
            raise ResearchError('Research request failed, HTTP ' + str(exc.code) + '. No automatic retry.') from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise ResearchError('Research request failed or returned invalid JSON. No automatic retry.') from None
        if not isinstance(result, dict) or result.get('success') is not True:
            raise ResearchError('API did not confirm success. Result discarded.')
        charged = result.get('credits_charged', 1)
        if type(charged) is not int or charged < 0:
            raise ResearchError('Unexpected credit accounting. Stop for review.')
        self.actual_credits += charged
        if charged > 1:
            # Provider pricing cannot be enforced locally after an unexpected charge.
            self.approved_credits = self.reserved_credits
            raise ResearchError('Provider charged more than the reserved cost. Stop and review pricing.')
        stamp = self.clock()
        self.cache_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        temp = cache_path.with_suffix('.tmp')
        temp.write_text(json.dumps({'fetched_at': stamp, 'response': result}))
        temp.chmod(0o600)
        temp.replace(cache_path)
        self.receipts.append({'endpoint': path, 'cache_hit': False, 'fetched_at': stamp,
                              'reserved_credits': 1, 'charged_credits': charged})
        return result

    def usage(self):
        return {'approved_credits': self.approved_credits, 'reserved_credits': self.reserved_credits,
                'actual_credits': self.actual_credits, 'cache_hits': self.cache_hits}
