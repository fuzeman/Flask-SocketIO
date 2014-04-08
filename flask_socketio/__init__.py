from gevent import monkey

monkey.patch_all()

from socketio import socketio_manage
from socketio.server import SocketIOServer
from flask import request, session
from flask.ext.socketio.namespace import FlaskNamespace
from werkzeug.debug import DebuggedApplication
from werkzeug.serving import run_with_reloader
from test_client import SocketIOTestClient


class SocketIOMiddleware(object):
    def __init__(self, app, socket, **kwargs):
        self.app = app
        if app.debug:
            app.wsgi_app = DebuggedApplication(app.wsgi_app, evalex=True)
        self.wsgi_app = app.wsgi_app
        self.socket = socket

        self.kwargs = kwargs

    def __call__(self, environ, start_response):
        path = environ['PATH_INFO'].strip('/')

        if path is not None and path.startswith('socket.io'):
            environ['flask_socketio'] = self.socket

            socketio_manage(
                environ,
                self.socket.get_namespaces(),
                self.app,

                **self.kwargs
            )
        else:
            return self.wsgi_app(environ, start_response)

class SocketIO(object):
    def __init__(self, app=None, ns_base=FlaskNamespace, **kwargs):
        if app:
            self.init_app(app, **kwargs)

        self.ns_base = ns_base

        self.namespaces = {}
        self.messages = {}
        self.rooms = {}

    def init_app(self, app, **kwargs):
        app.wsgi_app = SocketIOMiddleware(app, self, **kwargs)

    def get_namespaces(self):
        for ns_name in self.messages.keys():
            if ns_name in self.namespaces:
                continue

            self.namespaces[ns_name] = self.ns_base

        return self.namespaces

    def _dispatch_message(self, app, namespace, message, args=[]):
        if namespace.ns_name not in self.messages:
            return
        if message not in self.messages[namespace.ns_name]:
            return
        with app.request_context(namespace.environ):
            request.namespace = namespace
            for k, v in namespace.session.items():
                session[k] = v
            ret = self.messages[namespace.ns_name][message](*args)
            for k, v in session.items():
                namespace.session[k] = v
            return ret

    def _join_room(self, namespace, room):
        if namespace.ns_name not in self.rooms:
            self.rooms[namespace.ns_name] = {}
        if room not in self.rooms[namespace.ns_name]:
            self.rooms[namespace.ns_name][room] = set()
        if namespace not in self.rooms[namespace.ns_name][room]:
            self.rooms[namespace.ns_name][room].add(namespace)
            return True
        return False

    def _leave_room(self, namespace, room):
        if namespace.ns_name in self.rooms:
            if room in self.rooms[namespace.ns_name]:
                if namespace in self.rooms[namespace.ns_name][room]:
                    self.rooms[namespace.ns_name][room].remove(namespace)
                    if len(self.rooms[namespace.ns_name][room]) == 0:
                        del self.rooms[namespace.ns_name][room]
                        if len(self.rooms[namespace.ns_name]) == 0:
                            del self.rooms[namespace.ns_name]

                    return True
        return False
        
    def on_message(self, message, handler, **options):
        ns_name = options.pop('namespace', '')
        if ns_name not in self.messages:
            self.messages[ns_name] = {}
        self.messages[ns_name][message] = handler

    def on(self, message, **options):
        def decorator(f):
            self.on_message(message, f, **options)
            return f
        return decorator

    def emit(self, event, *args, **kwargs):
        ns_name = kwargs.pop('namespace', None)
        if ns_name is None:
            ns_name = ''
        room = kwargs.pop('room', None)
        if room:
            for client in self.rooms.get(ns_name, {}).get(room, set()):
                super(FlaskNamespace, client).emit(event, *args, **kwargs)
        else:
            for sessid, socket in self.server.sockets.items():
                if socket.active_ns.get(ns_name):
                    super(FlaskNamespace, socket[ns_name]).emit(event, *args, **kwargs)

    def send(self, message, json=False, namespace=None, room=None):
        ns_name = namespace
        if ns_name is None:
            ns_name = ''
        if room:
            for client in self.rooms.get(ns_name, {}).get(room, set()):
                super(FlaskNamespace, client).send(message, json)
        else:
            for sessid, socket in self.server.sockets.items():
                if socket.active_ns.get(ns_name):
                    super(FlaskNamespace, socket[ns_name]).send(message, json)

    def run(self, app, host=None, port=None, **kwargs):
        if host is None:
            host = '127.0.0.1'
        if port is None:
            server_name = app.config['SERVER_NAME']
            if server_name and ':' in server_name:
                port = int(server_name.rsplit(':', 1)[1])
            else:
                port = 5000
        #Don't allow override of resource, otherwise allow SocketIOServer kwargs to be passed through
        kwargs.pop('resource', None)
        self.server = SocketIOServer((host, port), app.wsgi_app, resource='socket.io', **kwargs)
        if app.debug:
            @run_with_reloader
            def run_server():
                self.server.serve_forever()
            run_server()
        else:
            self.server.serve_forever()

    def test_client(self, app, namespace=None):
        return SocketIOTestClient(app, self, namespace)


def emit(event, *args, **kwargs):
    return request.namespace.emit(event, *args, **kwargs)

def send(message, json=False, namespace=None, callback=None, broadcast=False, room=None):
    return request.namespace.send(message, json, namespace, callback, broadcast, room)


def join_room(room):
    return request.namespace.join_room(room)


def leave_room(room):
    return request.namespace.leave_room(room)


def error(error_name, error_message, msg_id=None, quiet=False):
    return request.namespace.error(error_name, error_message, msg_id, quiet)


def disconnect(silent=False):
    return request.namespace.disconnect(silent)
