import copy
from lib.rome.core.session.session import Session as RomeSession

class RomeTransactionContext():
    def __init__(self, user_id=None, project_id=None,
                 is_admin=None, read_deleted="no",
                 roles=None, remote_address=None, timestamp=None,
                 request_id=None, auth_token=None, overwrite=True,
                 quota_class=None, user_name=None, project_name=None,
                 service_catalog=None, instance_lock_checked=False,
                 user_auth_plugin=None, mode=None, **kwargs):
        self.is_admin = is_admin if is_admin else False
        self.user_id = user_id
        self.project_id = project_id
        self.read_deleted = read_deleted
        if not mode:
            self.writer = RomeTransactionContext(mode="writer")
            self.reader = RomeTransactionContext(mode="reader")
        pass

class RomeRequestContext(object):
    def __init__(self, user_id=None, project_id=None,
                 is_admin=None, read_deleted="no",
                 roles=None, remote_address=None, timestamp=None,
                 request_id=None, auth_token=None, overwrite=True,
                 quota_class=None, user_name=None, project_name=None,
                 service_catalog=None, instance_lock_checked=False,
                 user_auth_plugin=None, **kwargs):
        self.session = RomeSession()
        self.user_id = user_id
        self.project_id = project_id
        self.is_admin = is_admin
        self.read_deleted = read_deleted
        self.roles = roles or []
        self.remote_address = remote_address
        self.timestamp = timestamp
        self.request_id = request_id
        self.auth_token = auth_token
        self.overwrite = overwrite
        self.quota_class = quota_class
        self.user_name = user_name
        self.project_name = project_name
        self.service_catalog = service_catalog
        self.instance_lock_checked = instance_lock_checked
        self.user_auth_plugin = user_auth_plugin


    def load_context(self, context):
        filter_attributes = ["session"]
        for (attr_name, attr_value) in context.__dict__.iteritems():
            if attr_name not in filter_attributes:
                # print(attr_name)
                setattr(self, attr_name, attr_value)


    def elevated(self, read_deleted=None):
        """Return a version of this context with admin flag set."""
        context = copy.copy(self)
        # context.roles must be deepcopied to leave original roles
        # without changes

        context.roles = copy.deepcopy(self.roles)
        context.is_admin = True

        if 'admin' not in context.roles:
            context.roles.append('admin')

        if read_deleted is not None:
            context.read_deleted = read_deleted

        return context

def get_admin_context(read_deleted="no"):
    return RomeRequestContext(user_id=None,
                          project_id=None,
                          is_admin=True,
                          read_deleted=read_deleted,
                          overwrite=False)

class RomeContextManager(object):
    pass