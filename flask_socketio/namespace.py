from flask import request
from socketio.namespace import BaseNamespace


class FlaskNamespace(BaseNamespace):
    def __init__(self, environ, ns_name, request=None):
        super(FlaskNamespace, self).__init__(environ, ns_name, request)

        self.socketio = environ['flask_socketio']

    def initialize(self):

        self.rooms = set()

    def process_event(self, packet):
        name = packet['name']
        args = packet['args']

        if not self.is_method_allowed(name):
            self.error('method_access_denied',
                       'You do not have access to method "%s"' % name)
            return

        self.socketio._dispatch_message(self.request, self, name, args)

    def join_room(self, room):
        if self.socketio._join_room(self, room):
            self.rooms.add(room)

    def leave_room(self, room):
        if self.socketio._leave_room(self, room):
            self.rooms.remove(room)

    def recv_connect(self):
        ret = super(FlaskNamespace, self).recv_connect()
        app = self.request
        self.socketio._dispatch_message(app, self, 'connect')
        return ret

    def recv_disconnect(self):
        app = self.request
        self.socketio._dispatch_message(app, self, 'disconnect')
        for room in self.rooms.copy():
            self.leave_room(room)
        return super(FlaskNamespace, self).recv_disconnect()

    def recv_message(self, data):
        app = self.request
        return self.socketio._dispatch_message(app, self, 'message', [data])

    def recv_json(self, data):
        app = self.request
        return self.socketio._dispatch_message(app, self, 'json', [data])

    def emit(self, event, *args, **kwargs):
        ns_name = kwargs.pop('namespace', None)
        broadcast = kwargs.pop('broadcast', False)
        room = kwargs.pop('room', None)

        if broadcast or room:
            if ns_name is None:
                ns_name = self.ns_name

            return self.socketio.emit(event, *args, namespace=ns_name, room=room)

        if ns_name is None:
            return super(FlaskNamespace, self).emit(event, *args, **kwargs)

        return super(FlaskNamespace, request.namespace.socket[ns_name]).emit(event, *args, **kwargs)

    def send(self, message, json=False, ns_name=None, callback=None,
             broadcast=False, room=None):

        if broadcast or room:
            if ns_name is None:
                ns_name = self.ns_name

            return self.socketio.send(message, json, ns_name, room)

        if ns_name is None:
            return super(FlaskNamespace, request.namespace).send(message, json, callback)

        return super(FlaskNamespace, request.namespace.socket[ns_name]).send(message, json, callback)
