"""Desimplifier module.

This module contains functions, classes and mix-in that are used for the
def simplifcation of objects, before sending them to the services of nova.

"""

import datetime
import riak
import netaddr
import pytz
import models
import lazy_reference

db_client = riak.RiakClient(pb_port=8087, protocol='pbc')

def convert_to_camelcase(word):
    """Convert the given word into camelcase naming convention."""
    return ''.join(x.capitalize() or '_' for x in word.split('_'))

class ObjectDesimplifier(object):
    """Class that translate an object containing values taken from database
    into an object containing values understandable by services composing
    Nova."""

    def __init__(self):
        """Constructor"""
        self.cache = {}

    def is_dict_and_has_key(self, obj, key):
        """Check if the given object is a dict which contains the given key."""
        if isinstance(obj, dict):
            return obj.has_key(key)
        return False

    def get_key(self, obj):
        """Returns a unique key for the given object."""
        if self.is_dict_and_has_key(obj, "tablename"):
            table_name = obj["tablename"]
            key = obj["id"]
            return "%s-%s" % (table_name, str(key))
        else:
            return "%s-%s" % (hex(id(obj)), hex(id(obj)))

    def spawn_empty_model(self, obj):
        """Spawn an empty instance of the model class specified by the
        given object"""

        if "novabase_classname" in obj:
            model_class_name = obj["novabase_classname"]
        elif "metadata_novabase_classname" in obj:
            model_class_name = obj["metadata_novabase_classname"]

        if model_class_name is not None:
            model = models.get_model_class_from_name(model_class_name)
            model_object = model()
            if not self.cache.has_key(self.get_key(obj)):
                self.cache[self.get_key(obj)] = model_object
            return self.cache[self.get_key(obj)]
        else:
            return None

    def update_nova_model(self, obj):
        """Update the fields of the given object."""

        key = self.get_key(obj)
        current_model = self.cache[key]

        # Check if obj is simplified or not
        if "simplify_strategy" in obj:
            object_bucket = db_client.bucket(obj["tablename"])
            riak_value = object_bucket.get(str(obj["id"]))
            obj = riak_value.data

        # For each value of obj, set the corresponding attributes.
        for key in obj:
            simplified_value = self.desimplify(obj[key])
            try:
                if simplified_value is not None:
                    setattr(current_model, key, self.desimplify(obj[key]))
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

    def novabase_desimplify(self, obj):
        """Desimplify a novabase object."""

        key = self.get_key(obj)
        if not self.cache.has_key(key):
            if obj.has_key("nova_classname"):
                tablename = obj["nova_classname"]
            elif obj.has_key("novabase_classname"):
                tablename = models.get_tablename_from_name(
                    obj["novabase_classname"]
                )
            else:
                tablename = models.get_tablename_from_name(
                    obj["metadata_novabase_classname"]
                )
            self.cache[key] = lazy_reference.LazyReference(
                tablename,
                obj["id"]
            )

        return self.cache[key]


    def datetime_desimplify(self, value):
        """Desimplify a datetime object."""

        result = datetime.datetime.strptime(value["value"], '%b %d %Y %H:%M:%S')
        if value["timezone"] == "UTC":
            result = pytz.utc.localize(result)
        return result

    def ipnetwork_desimplify(self, value):
        """Desimplify an IPNetwork object."""

        return netaddr.IPNetwork(value["value"])

    def desimplify(self, obj):
        """Apply the best desimplification strategy on the given object."""

        result = obj

        is_dict = isinstance(obj, dict)
        is_list = isinstance(obj, list)

        if self.is_dict_and_has_key(obj, "simplify_strategy"):
            if obj['simplify_strategy'] == 'datetime':
                result = self.datetime_desimplify(obj)
            if obj['simplify_strategy'] == 'ipnetwork':
                result = self.ipnetwork_desimplify(obj)
            if obj['simplify_strategy'] == 'novabase':
                result = self.novabase_desimplify(obj)
        elif is_list:
            list_result = []
            for item in obj:
                list_result += [self.desimplify(item)]
            result = list_result
        elif is_dict and obj.has_key("novabase_classname"):
            result = self.novabase_desimplify(obj)
        elif is_dict and obj.has_key("metadata_novabase_classname"):
            result = self.novabase_desimplify(obj)

        return result
