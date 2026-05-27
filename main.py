import os
import logging
from ulauncher.api.client.Extension import Extension
from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent, PreferencesEvent, PreferencesUpdateEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction
from gtask_client import GoogleTasksAuth, GoogleTasksClient

logger = logging.getLogger(__name__)
DIR = os.path.dirname(os.path.abspath(__file__))
ICON = 'images/icon.svg'
CHECKED = 'images/checked.svg'


def strikethrough(text):
    return '\u0336'.join(text) + '\u0336'


def item(name, description='', icon=ICON, data=None, on_enter=None):
    return ExtensionResultItem(
        icon=icon,
        name=name,
        description=description,
        on_enter=on_enter or ExtensionCustomAction(data or {}, keep_app_open=True),
    )


def render(items):
    return RenderResultListAction(items)


class GTaskExtension(Extension):
    def __init__(self):
        super().__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())
        self.subscribe(PreferencesEvent, PreferencesEventListener())
        self.subscribe(PreferencesUpdateEvent, PreferencesUpdateEventListener())
        self.auth = None
        self.client = None
        self.selected_list_id = None
        self.selected_list_title = None
        self.preferences = {}
        self._auth_attempted = False

    def init_client(self):
        self.auth = GoogleTasksAuth(os.path.join(DIR, 'credentials.json'), os.path.join(DIR, 'token.json'))
        if self.auth.is_authenticated():
            self.client = GoogleTasksClient(self.auth)
            return True
        return False


class PreferencesEventListener(EventListener):
    def on_event(self, event, extension):
        extension.preferences = event.preferences
        if not extension._auth_attempted:
            extension._auth_attempted = True
            extension.init_client()


class PreferencesUpdateEventListener(EventListener):
    def on_event(self, event, extension):
        extension.preferences[event.id] = event.new_value


class KeywordQueryEventListener(EventListener):
    def on_event(self, event, extension):
        query = (event.get_argument() or '').strip()

        if not extension.auth or not extension.auth.is_authenticated():
            return self._render_not_authenticated(extension)
        if not extension.client:
            return render([item('Failed to initialize Google Tasks client', on_enter=DoNothingAction())])

        if not query:
            return self._list_tasks(extension, '') if extension.selected_list_id else self._list_tasklists(extension, '')

        if query.lower() == 'back':
            extension.selected_list_id = None
            extension.selected_list_title = None
            return self._list_tasklists(extension, '')

        if query.lower().startswith('add '):
            title = query[4:].strip()
            return self._add_task(extension, title) if title else render([
                item('Usage: add <task title>', on_enter=DoNothingAction())
            ])

        if extension.selected_list_id:
            return self._list_tasks(extension, query)
        return self._list_tasklists(extension, query)

    def _render_not_authenticated(self, extension):
        if not extension.auth:
            extension.init_client()
        if not extension.auth or not extension.auth.has_credentials():
            return render([
                item('credentials.json not found',
                     description=f'Place Google OAuth credentials at: {os.path.join(DIR, "credentials.json")}',
                     on_enter=DoNothingAction())
            ])
        return render([
            item('Sign in with Google', description='Click to authorize Google Tasks access',
                 data={'action': 'auth'})
        ])

    def _list_tasklists(self, extension, search):
        try:
            lists = extension.client.list_tasklists().get('items', [])
        except Exception as e:
            logger.error(f'Failed to list task lists: {e}')
            return render([item(str(e), on_enter=DoNothingAction())])

        if search:
            q = search.lower()
            lists = [tl for tl in lists if q in tl['title'].lower()]

        return render([
            item(tl['title'], 'Google Task List', data={'action': 'select_list', 'list_id': tl['id'], 'list_title': tl['title']})
            for tl in lists
        ]) if lists else render([
            item('No task lists found', 'Create one in Google Tasks, then refresh', on_enter=DoNothingAction())
        ])

    def _list_tasks(self, extension, search):
        try:
            show_completed = extension.preferences.get('show_completed', 'Hide') == 'Show'
            tasks = extension.client.list_tasks(extension.selected_list_id, show_completed).get('items', [])
        except Exception as e:
            logger.error(f'Failed to list tasks: {e}')
            return render([item(str(e), on_enter=DoNothingAction())])

        if search:
            q = search.lower()
            tasks = [t for t in tasks if q in t['title'].lower()]

        items = [item('\u2190 Back to lists', extension.selected_list_title or 'Task Lists',
                      data={'action': 'back'})]
        for task in tasks:
            is_completed = task.get('status') == 'completed'
            notes = (task.get('notes') or '')[:100]
            due = task.get('due', '')
            desc = ' | '.join(filter(None, [f'Due: {due[:10]}' if due else '', notes]))
            items.append(item(
                strikethrough(task['title']) if is_completed else task['title'],
                desc,
                CHECKED if is_completed else ICON,
                data={'action': 'delete' if is_completed else 'complete',
                      'task_id': task['id'], 'task_title': task['title'],
                      'list_id': extension.selected_list_id},
            ))
        if len(items) == 1:
            items.append(item('No tasks found', 'Type "add <task>" to create a new task', on_enter=DoNothingAction()))
        return render(items)

    def _add_task(self, extension, title):
        try:
            list_id = extension.selected_list_id
            if not list_id:
                default = extension.preferences.get('default_list', '')
                if default:
                    list_id = default
                else:
                    lists = extension.client.list_tasklists().get('items', [])
                    if not lists:
                        return render([item('No task lists available', on_enter=DoNothingAction())])
                    list_id = lists[0]['id']
            extension.client.insert_task(list_id, title)
            if extension.selected_list_id:
                return self._list_tasks(extension, '')
            return render([item(f'Task added: {title}')])
        except Exception as e:
            logger.error(f'Failed to add task: {e}')
            return render([item(str(e), on_enter=DoNothingAction())])


class ItemEnterEventListener(EventListener):
    def on_event(self, event, extension):
        data = event.get_data()
        action = data.get('action') if data else None
        kw = KeywordQueryEventListener()

        if action == 'auth':
            try:
                extension.init_client()
                if extension.auth and not extension.auth.is_authenticated():
                    extension.auth.load_credentials()
                    extension.auth.authenticate()
                    extension.client = GoogleTasksClient(extension.auth)
                return render([item('Authenticated! Type your keyword to get started.')])
            except Exception as e:
                logger.error(f'Auth failed: {e}')
                return render([item(f'Authentication failed: {e}', on_enter=DoNothingAction())])

        if action == 'select_list':
            extension.selected_list_id = data['list_id']
            extension.selected_list_title = data['list_title']
            return kw._list_tasks(extension, '')

        if action == 'back':
            extension.selected_list_id = None
            extension.selected_list_title = None
            return kw._list_tasklists(extension, '')

        if action == 'complete':
            try:
                extension.client.complete_task(data['list_id'], data['task_id'])
                return kw._list_tasks(extension, '')
            except Exception as e:
                return render([item(f'Failed to complete task: {e}', on_enter=DoNothingAction())])

        if action == 'delete':
            try:
                extension.client.delete_task(data['list_id'], data['task_id'])
                return kw._list_tasks(extension, '')
            except Exception as e:
                return render([item(f'Failed to delete task: {e}', on_enter=DoNothingAction())])

        return render([item('Unknown action', on_enter=DoNothingAction())])


if __name__ == '__main__':
    GTaskExtension().run()
