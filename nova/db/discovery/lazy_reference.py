
# RIAK
import riak

from models import get_model_class_from_name
import time
import traceback

from nova.db.discovery.models import get_model_classname_from_tablename
from nova.db.discovery.models import get_model_tablename_from_classname

dbClient = riak.RiakClient(pb_port=8087, protocol='pbc')

def now_in_ms():
    return int(round(time.time() * 1000))

class EmptyObject:
    pass

class LazyReference:

    def __init__(self, base, id, desimplifier=None):
        """Constructor"""
        self._base = base
        self._id = id

        self.cache = {}

        if desimplifier is None:
            from desimplifier import ObjectDesimplifier
            self.desimplifier = ObjectDesimplifier()
        else:
            self.desimplifier = desimplifier

    def get_key(self):
        return "%s_%s" % (self.resolve_model_name(), str(self._id))

    def resolve_model_name(self):
        return get_model_classname_from_tablename(self._base)

    def spawn_empty_model(self, obj):
        """Spawn an empty instance of the model class specified by the
        given object"""

        key = self.get_key()

        if "novabase_classname" in obj:
            model_class_name = obj["novabase_classname"]
        elif "metadata_novabase_classname" in obj:
            model_class_name = obj["metadata_novabase_classname"]

        if model_class_name is not None:
            model = get_model_class_from_name(model_class_name)
            model_object = model()
            if not self.cache.has_key(key):
                self.cache[key] = model_object
            return self.cache[key]
        else:
            return None

    def update_nova_model(self, obj):
        """Update the fields of the given object."""

        

        key = self.get_key()
        current_model = self.cache[key]

        # Check if obj is simplified or not
        if "simplify_strategy" in obj:
            object_bucket = db_client.bucket(obj["tablename"])
            riak_value = object_bucket.get(str(obj["id"]))
            obj = riak_value.data

        # For each value of obj, set the corresponding attributes.
        for key in obj:
            simplified_value = self.desimplifier.desimplify(obj[key])
            try:
                if simplified_value is not None:
                    setattr(current_model, key, self.desimplifier.desimplify(obj[key]))
                else:
                    setattr(current_model, key, obj[key])
            except Exception as e:
                if "None is not list-like" in str(e):
                    setattr(current_model, key, [])
                else:
                    pass

        if hasattr(current_model, "user_id") and obj.has_key("user_id"):
            current_model.user_id = obj["user_id"]

        if hasattr(current_model, "project_id") and obj.has_key("project_id"):
            current_model.project_id = obj["project_id"]

        # Update foreign keys
        current_model.update_foreign_keys()

        return current_model

    def load(self):


        key = self.get_key()

        print("LOADING (%s)" % (key))

        key_index_bucket = dbClient.bucket(self._base)
        fetched = key_index_bucket.get(str(self._id))
        obj = fetched.data

        self.spawn_empty_model(obj)
        self.update_nova_model(obj)

        return self.cache[key]

    def get_complex_ref(self):

        key = self.get_key()       

        if not self.cache.has_key(key):
            self.load()            

        return self.cache[key]


    def __getattr__(self, item):
        return getattr(self.get_complex_ref(), item)

    def __str__(self):
        return "Lazy(%s)" % (self.get_key())

    def __repr__(self):
        return "Lazy(%s)" % (self.get_key())

    def __nonzero__(self):
        return not not self.get_complex_ref()
