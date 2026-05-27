import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event

logger = logging.getLogger(__name__)
SCOPES = ['https://www.googleapis.com/auth/tasks']


class OAuthHandler(BaseHTTPRequestHandler):
    auth_code = None
    auth_event = Event()

    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        status = 200
        if 'code' in params:
            self.server.auth_code = params['code'][0]
            body = b'<html><body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f0f4f8;"><div style="text-align:center;padding:40px;background:white;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.1);"><h1 style="color:#34a853;">Authentication Successful!</h1><p style="color:#5f6368;">You can close this window now.</p></div></body></html>'
        elif 'error' in params:
            status = 400
            body = b'<html><body><h1>Authentication failed</h1></body></html>'
        else:
            body = b'<html><body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f0f4f8;"><div style="text-align:center;padding:40px;background:white;border-radius:12px;box-shadow:0 4px 24px rgba(0,0,0,.1);"><h2 style="color:#5f6368;">Waiting for authorization...</h2></div></body></html>'
        self.send_response(status)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(body)
        if self.server.auth_code:
            self.server.auth_event.set()

    def log_message(self, format, *args):
        pass


def run_oauth_flow(client_id, client_secret):
    server = HTTPServer(('localhost', 0), OAuthHandler)
    port = server.server_address[1]
    redirect_uri = f'http://localhost:{port}/'

    webbrowser.open(
        f'https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode({
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(SCOPES),
            "access_type": "offline",
            "state": str(uuid.uuid4()),
            "prompt": "consent",
        })}'
    )

    server.handle_request()
    server.server_close()
    if not server.auth_code:
        raise Exception('OAuth authentication was cancelled or failed')

    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=urllib.parse.urlencode({
            'code': server.auth_code, 'client_id': client_id,
            'client_secret': client_secret, 'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }).encode(),
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )
    token = json.loads(urllib.request.urlopen(req).read().decode())
    token['expires_at'] = time.time() + token.get('expires_in', 3600)
    return token


class GoogleTasksAuth:
    def __init__(self, credentials_path, token_path):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.creds = None
        self.token_data = None
        if self.has_token():
            self.load_token()

    def has_credentials(self):
        return os.path.exists(self.credentials_path)

    def load_credentials(self):
        if not self.has_credentials():
            raise FileNotFoundError(f'credentials.json not found at {self.credentials_path}')
        with open(self.credentials_path) as f:
            self.creds = json.load(f)
        if 'installed' in self.creds:
            self.creds = self.creds['installed']
        return self.creds

    def has_token(self):
        return os.path.exists(self.token_path)

    def load_token(self):
        if self.has_token():
            with open(self.token_path) as f:
                self.token_data = json.load(f)

    def save_token(self, token):
        with open(self.token_path, 'w') as f:
            json.dump(token, f, indent=2)
        self.token_data = token

    def is_authenticated(self):
        return self.token_data is not None

    def get_access_token(self):
        if not self.token_data:
            return None
        if self.token_data.get('expires_at', 0) < time.time() + 60:
            self._refresh_token()
        return self.token_data['access_token']

    def _refresh_token(self):
        if not self.token_data or 'refresh_token' not in self.token_data:
            raise Exception('No refresh token available, re-authentication required')
        if not self.creds:
            self.load_credentials()
        req = urllib.request.Request(
            'https://oauth2.googleapis.com/token',
            data=urllib.parse.urlencode({
                'refresh_token': self.token_data['refresh_token'],
                'client_id': self.creds['client_id'],
                'client_secret': self.creds['client_secret'],
                'grant_type': 'refresh_token',
            }).encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        new_token = json.loads(urllib.request.urlopen(req).read().decode())
        new_token['refresh_token'] = new_token.get('refresh_token', self.token_data.get('refresh_token'))
        new_token['expires_at'] = time.time() + new_token.get('expires_in', 3600)
        self.save_token(new_token)

    def authenticate(self):
        if not self.creds:
            self.load_credentials()
        logger.info('Starting OAuth authentication flow...')
        self.save_token(run_oauth_flow(self.creds['client_id'], self.creds['client_secret']))
        logger.info('OAuth authentication successful')


class GoogleTasksClient:
    API_BASE = 'https://tasks.googleapis.com/tasks/v1'

    def __init__(self, auth, cache_path):
        self.auth = auth
        self.cache_path = cache_path
        self._cache = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path) as f:
                    self._cache = json.load(f)
            except Exception:
                self._cache = {'tasklists': [], 'tasks': {}}
        else:
            self._cache = {'tasklists': [], 'tasks': {}}

    def _save_cache(self):
        tmp = self.cache_path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self._cache, f, indent=2)
        os.replace(tmp, self.cache_path)

    def _cache_get_tasklists(self):
        return self._cache.get('tasklists', [])

    def _cache_set_tasklists(self, lists):
        self._cache['tasklists'] = lists
        self._save_cache()

    def _cache_get_tasks(self, tasklist_id):
        return self._cache.get('tasks', {}).get(tasklist_id, [])

    def _cache_set_tasks(self, tasklist_id, tasks):
        self._cache.setdefault('tasks', {})[tasklist_id] = tasks
        self._save_cache()

    def _request(self, method, path, body=None, params=None):
        access_token = self.auth.get_access_token()
        url = f'{self.API_BASE}{path}'
        if params:
            url += '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode() if body else None,
            headers={'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'},
            method=method,
        )
        try:
            raw = urllib.request.urlopen(req).read().decode()
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            if e.code == 401:
                self.auth._refresh_token()
                return self._request(method, path, body, params)
            error = e.read().decode() if e.fp else ''
            logger.error(f'API error ({e.code}): {error}')
            raise Exception(f'Google Tasks API error ({e.code}): {error}')

    def list_tasklists(self):
        cached = self._cache_get_tasklists()
        if cached:
            return {'items': cached}
        result = self._request('GET', '/users/@me/lists', params={'maxResults': 100})
        items = result.get('items', [])
        self._cache_set_tasklists(items)
        return result

    def list_tasks(self, tasklist_id, show_completed=True, max_results=None):
        cached = self._cache_get_tasks(tasklist_id)
        if cached:
            tasks = [t for t in cached if show_completed or t.get('status') != 'completed']
            if max_results is not None:
                tasks = tasks[:max_results]
            return {'items': tasks}
        result = self._request('GET', f'/lists/{tasklist_id}/tasks', params={
            'showHidden': 'true', 'showCompleted': 'true', 'maxResults': 100,
        })
        items = result.get('items', [])
        self._cache_set_tasks(tasklist_id, items)
        tasks = [t for t in items if show_completed or t.get('status') != 'completed']
        if max_results is not None:
            tasks = tasks[:max_results]
        return {'items': tasks}

    def insert_task(self, tasklist_id, title, notes=None, due=None):
        result = self._request('POST', f'/lists/{tasklist_id}/tasks', body={
            'title': title, 'status': 'needsAction',
            **({'notes': notes} if notes else {}),
            **({'due': due} if due else {}),
        })
        tasks = self._cache_get_tasks(tasklist_id)
        tasks.append(result)
        self._cache_set_tasks(tasklist_id, tasks)
        return result

    def complete_task(self, tasklist_id, task_id):
        result = self._request('PATCH', f'/lists/{tasklist_id}/tasks/{task_id}', body={'status': 'completed'})
        tasks = self._cache_get_tasks(tasklist_id)
        for t in tasks:
            if t['id'] == task_id:
                t['status'] = 'completed'
                break
        self._cache_set_tasks(tasklist_id, tasks)
        return result

    def delete_task(self, tasklist_id, task_id):
        self._request('DELETE', f'/lists/{tasklist_id}/tasks/{task_id}')
        tasks = self._cache_get_tasks(tasklist_id)
        self._cache_set_tasks(tasklist_id, [t for t in tasks if t['id'] != task_id])
        return {}

    def delete_tasklist(self, tasklist_id):
        self._request('DELETE', f'/users/@me/lists/{tasklist_id}')
        lists = self._cache_get_tasklists()
        self._cache['tasklists'] = [tl for tl in lists if tl['id'] != tasklist_id]
        self._cache['tasks'].pop(tasklist_id, None)
        self._save_cache()
        return {}

    def create_tasklist(self, title):
        result = self._request('POST', '/users/@me/lists', body={'title': title})
        lists = self._cache_get_tasklists()
        lists.append(result)
        self._cache_set_tasklists(lists)
        return result

    def uncomplete_task(self, tasklist_id, task_id):
        result = self._request('PATCH', f'/lists/{tasklist_id}/tasks/{task_id}', body={'status': 'needsAction'})
        tasks = self._cache_get_tasks(tasklist_id)
        for t in tasks:
            if t['id'] == task_id:
                t['status'] = 'needsAction'
                break
        self._cache_set_tasks(tasklist_id, tasks)
        return result

    def sync_all(self):
        lists_result = self._request('GET', '/users/@me/lists', params={'maxResults': 100})
        lists = lists_result.get('items', [])
        self._cache_set_tasklists(lists)
        for tl in lists:
            tasks_result = self._request('GET', f'/lists/{tl["id"]}/tasks', params={
                'showHidden': 'true', 'showCompleted': 'true', 'maxResults': 100,
            })
            self._cache_set_tasks(tl['id'], tasks_result.get('items', []))
        return lists_result
