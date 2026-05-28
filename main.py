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
LIST_ICON = 'images/list.svg'
BACK_ICON = 'images/back.svg'


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
        self.cache_path = os.path.join(DIR, 'cache.json')

    def init_client(self):
        self.auth = GoogleTasksAuth(os.path.join(DIR, 'credentials.json'), os.path.join(DIR, 'token.json'))
        if self.auth.is_authenticated():
            self.client = GoogleTasksClient(self.auth, self.cache_path)
            if not os.path.exists(self.cache_path):
                self.client.sync_all()
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
            return (self._list_tasks if extension.selected_list_id else self._list_tasklists)(extension, '')

        parts = query.split(' ', 1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ''

        if cmd == 'back':
            extension.selected_list_id = None
            extension.selected_list_title = None
            return self._list_tasklists(extension, '')

        if cmd == 'new':
            return self._add_task(extension, arg)

        if cmd == 'newlist':
            return self._create_list(extension, arg)

        if cmd == 'del':
            if not extension.selected_list_id:
                return render([item('Use this command inside a task list', on_enter=DoNothingAction())])
            return self._show_delete_targets(extension, arg)

        if cmd == 'dellist':
            if extension.selected_list_id:
                return render([item('Use "back" first, then "dellist"', on_enter=DoNothingAction())])
            return self._show_dellist_targets(extension, arg)

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
            item(tl['title'], 'Google Task List', icon=LIST_ICON,
                 data={'action': 'select_list', 'list_id': tl['id'], 'list_title': tl['title']})
            for tl in lists
        ]) if lists else render([
            item('No task lists found', 'Create one in Google Tasks, then refresh', on_enter=DoNothingAction())
        ])

    def _list_tasks(self, extension, search):
        try:
            show_completed = extension.preferences.get('show_completed', 'Hide') == 'Show'
            result_limit = extension.preferences.get('result_limit', '').strip()
            try:
                max_results = int(result_limit) if result_limit else None
            except ValueError:
                max_results = None
            tasks = extension.client.list_tasks(extension.selected_list_id, show_completed, max_results).get('items', [])
        except Exception as e:
            logger.error(f'Failed to list tasks: {e}')
            return render([item(str(e), on_enter=DoNothingAction())])

        if search:
            q = search.lower()
            tasks = [t for t in tasks if q in t['title'].lower()]

        items = [item('Back to lists', extension.selected_list_title or 'Task Lists',
                      icon=BACK_ICON, data={'action': 'back'})]
        for task in tasks:
            is_completed = task.get('status') == 'completed'
            notes = (task.get('notes') or '')[:100]
            due = task.get('due', '')
            desc = ' | '.join(filter(None, [f'Due: {due[:10]}' if due else '', notes]))
            items.append(item(
                strikethrough(task['title']) if is_completed else task['title'],
                desc,
                CHECKED if is_completed else ICON,
                data={'action': 'uncomplete' if is_completed else 'complete',
                      'task_id': task['id'], 'task_title': task['title'],
                      'list_id': extension.selected_list_id},
            ))
        if len(items) == 1:
            items.append(item('No tasks found', 'Type "new <task>" to create a new task', on_enter=DoNothingAction()))
        return render(items)

    def _add_task(self, extension, title):
        if not title:
            return render([item('Usage: new <task title>', on_enter=DoNothingAction())])
        return render([item(f'Create task: "{title}"', 'Click to confirm',
                             data={'action': 'new_confirm', 'title': title})])

    def _create_list(self, extension, title):
        if not title:
            return render([item('Usage: newlist <list name>', on_enter=DoNothingAction())])
        return render([item(f'Create list: "{title}"', 'Click to confirm',
                             data={'action': 'newlist_confirm', 'title': title})])

    def _show_delete_targets(self, extension, search):
        try:
            tasks = extension.client.list_tasks(extension.selected_list_id, show_completed=True).get('items', [])
        except Exception as e:
            return render([item(str(e), on_enter=DoNothingAction())])

        if search:
            q = search.lower()
            tasks = [t for t in tasks if q in t['title'].lower()]

        items = [item('Back to lists', extension.selected_list_title or 'Task Lists',
                      icon=BACK_ICON, data={'action': 'back'})]
        if not tasks:
            items.append(item('No tasks found', on_enter=DoNothingAction()))
        for task in tasks:
            is_completed = task.get('status') == 'completed'
            items.append(item(
                strikethrough(task['title']) if is_completed else task['title'],
                'Click to delete this task',
                CHECKED if is_completed else ICON,
                data={'action': 'delete_click', 'task_id': task['id'], 'task_title': task['title'],
                      'list_id': extension.selected_list_id},
            ))
        return render(items)

    def _show_dellist_targets(self, extension, search):
        try:
            lists = extension.client.list_tasklists().get('items', [])
        except Exception as e:
            return render([item(str(e), on_enter=DoNothingAction())])

        if search:
            q = search.lower()
            lists = [tl for tl in lists if q in tl['title'].lower()]

        return render([
            item(tl['title'], 'Click to delete this list (all tasks lost)', icon=LIST_ICON,
                 data={'action': 'dellist_click', 'list_id': tl['id'], 'list_title': tl['title']})
            for tl in lists
        ]) if lists else render([
            item('No task lists found', on_enter=DoNothingAction())
        ])


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
                    extension.cache_path = os.path.join(DIR, 'cache.json')
                    extension.client = GoogleTasksClient(extension.auth, extension.cache_path)
                    extension.client.sync_all()
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
                return render([item(f'Failed: {e}', on_enter=DoNothingAction())])

        if action == 'uncomplete':
            try:
                extension.client.uncomplete_task(data['list_id'], data['task_id'])
                return kw._list_tasks(extension, '')
            except Exception as e:
                return render([item(f'Failed: {e}', on_enter=DoNothingAction())])

        if action == 'new_confirm':
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
                extension.client.insert_task(list_id, data['title'])
                if extension.selected_list_id:
                    return kw._list_tasks(extension, '')
                return render([item(f'Task added: {data["title"]}')])
            except Exception as e:
                logger.error(f'Failed to add task: {e}')
                return render([item(str(e), on_enter=DoNothingAction())])

        if action == 'newlist_confirm':
            try:
                extension.client.create_tasklist(data['title'])
                return kw._list_tasklists(extension, '')
            except Exception as e:
                logger.error(f'Failed to create list: {e}')
                return render([item(str(e), on_enter=DoNothingAction())])

        if action == 'delete_click':
            return render([
                item(data['task_title'], 'Click again to confirm deletion',
                     data={'action': 'delete_confirm', 'task_id': data['task_id'],
                           'list_id': data['list_id']})
            ])

        if action == 'delete_confirm':
            try:
                extension.client.delete_task(data['list_id'], data['task_id'])
                return kw._list_tasks(extension, '')
            except Exception as e:
                return render([item(f'Failed: {e}', on_enter=DoNothingAction())])

        if action == 'dellist_click':
            return render([
                item(data['list_title'], 'All tasks in this list will be lost. Click again to confirm.',
                     data={'action': 'dellist_confirm', 'list_id': data['list_id']})
            ])

        if action == 'dellist_confirm':
            try:
                extension.client.delete_tasklist(data['list_id'])
                return kw._list_tasklists(extension, '')
            except Exception as e:
                return render([item(f'Failed: {e}', on_enter=DoNothingAction())])

        return render([item('Unknown action', on_enter=DoNothingAction())])


if __name__ == '__main__':
    GTaskExtension().run()
