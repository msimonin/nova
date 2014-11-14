from models import get_model_class_from_name
import datetime
import riak
# RIAK
import itertools
import traceback
import uuid
import pprint
import riak
import inspect
from inspect import getmembers
from sqlalchemy.util._collections import KeyedTuple
import netaddr
from sqlalchemy.sql.expression import BinaryExpression
from sqlalchemy.orm.evaluator import EvaluatorCompiler
from sqlalchemy.orm.collections import InstrumentedList
from nova.db.discovery import models
import pytz

try:
    from query import RiakModelQuery
except:
    pass

dbClient = riak.RiakClient(pb_port=8087, protocol='pbc')

class Context:
  is_admin = True

context = Context()

def convert_to_camelcase(word):
    return ''.join(x.capitalize() or '_' for x in word.split('_'))


def find_table_name(model):

    """This function returns the name of the given model as a String. If the
    model cannot be identified, it returns "none".
    :param model: a model object candidate
    :return: the table name or "none" if the object cannot be identified
    """

    if hasattr(model, "__tablename__"):
        return model.__tablename__

    if hasattr(model, "table"):
        return model.table.name

    if hasattr(model, "class_"):
        return model.class_.__tablename__

    if hasattr(model, "clauses"):
        for clause in model.clauses:
            return self.find_table_name(clause)

    return "none"

class ObjectDesimplifier:
    def __init__(self):
        self._simple_to_model_dict = {}
        pass

    def is_dict_and_has_key(self, obj, key):
        if isinstance(obj, dict):
            return obj.has_key(key)
        return False

    def get_key(self, obj):

        if self.is_dict_and_has_key(obj, "tablename"):
            table_name = obj["tablename"]
            key = obj["id"]
            return "%s-%s" % (table_name, str(key))
        else:
            return "%s-%s" % (hex(id(obj)), hex(id(obj)))

    def prepare_nova_model(self, obj):

        if "novabase_classname" in obj:
            model_class_name = obj["novabase_classname"]
            model = get_model_class_from_name(model_class_name)

            model_object = model()

            if not self._simple_to_model_dict.has_key(self.get_key(obj)):
                self._simple_to_model_dict[self.get_key(obj)] = model_object

            return self._simple_to_model_dict[self.get_key(obj)]

        elif "metadata_novabase_classname" in obj:
            model_class_name = obj["metadata_novabase_classname"]
            model = get_model_class_from_name(model_class_name)

            model_object = model()

            if not self._simple_to_model_dict.has_key(self.get_key(obj)):
                self._simple_to_model_dict[self.get_key(obj)] = model_object

            return self._simple_to_model_dict[self.get_key(obj)]
        else:
            return None

    def update_relationship_field(self, target, table_name, foreign_key, remote_field_name, foreign_key_value):

        key_index_bucket = dbClient.bucket("key_index")
        fetched = key_index_bucket.get(table_name)
        keys = fetched.data

        result = []
        if keys != None:
            for key in keys:
                try:
                    key_as_string = "%d" % (key)
                    
                    model_object = self.get_single_object(model, key)       

                    if hasattr(model_object, remote_field_name) and getattr(model_object, remote_field_name) == foreign_key_value:
                        result = result + [model_object]

                except Exception as ex:
                    print("problem with key: %s" %(key))
                    traceback.print_exc()
                    pass
        
        if len(result) > 0:
            first_result = result[0]

            setattr(obj, foreign_key, first_result)


        pass

    def update_foreign_keys(self, obj):

        if hasattr(obj, "metadata"):
            metadata = obj.metadata
            tablename = find_table_name(obj)

            if metadata and tablename in metadata.tables:
                for fk in metadata.tables[tablename].foreign_keys:
                    local_field_name = str(fk.parent).split(".")[-1]
                    remote_table_name = fk._colspec.split(".")[-2]
                    remote_field_name = fk._colspec.split(".")[-1]

                    if hasattr(obj, remote_table_name):
                        pass
                    else:
                        """ remove the "s" at the end of the tablename """
                        remote_table_name = remote_table_name[:-1]
                        pass

                    need_to_update_from_remote_object = False
                    try:
                        if not obj is None:
                            remote_object = getattr(obj, remote_table_name)
                            if remote_object is not None:
                                remote_field_value = getattr(remote_object, remote_field_name)
                                setattr(obj, local_field_name, remote_field_value)
                            else:
                                need_to_update_from_remote_object = True

                    except Exception as e:
                        need_to_update_from_remote_object = True
                        current_local_value = None

                    if need_to_update_from_remote_object and hasattr(obj, local_field_name):
                        current_local_value = getattr(obj, local_field_name)
                        remote_model_name = "".join([x.capitalize() for x in remote_table_name.split("_")])
                        remote_model_class = get_model_class_from_name(remote_model_name)

                        self.update_relationship_field(obj, remote_table_name, remote_table_name, remote_field_name, current_local_value)



    def update_nova_model(self, obj):
        current_model = self.prepare_nova_model(obj)

        # check if obj is simplified or not
        if "simplify_strategy" in obj:
            object_bucket = dbClient.bucket(obj["tablename"])
            riak_value = object_bucket.get(str(obj["id"]))
            obj = riak_value.data

        # print("update_nova_model(%s) <- %s" %(current_model, obj))
        
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
                    print("%s with %s" % (e, key))
                    traceback.print_exc()
                pass

        if hasattr(current_model, "user_id") and obj.has_key("user_id"):
            current_model.user_id = obj["user_id"]

        if hasattr(current_model, "project_id") and obj.has_key("project_id"):
            current_model.project_id = obj["project_id"]

        """ Update foreign keys """
        self.update_foreign_keys(current_model)

        return current_model

    def novabase_desimplify(self, obj):

        if self._simple_to_model_dict.has_key(self.get_key(obj)):
            return self._simple_to_model_dict[self.get_key(obj)]

        table_name = obj["tablename"]
        key = obj["id"]

        object_bucket = dbClient.bucket(table_name)
        riak_value = object_bucket.get(str(key))

        return self.update_nova_model(obj)


    def datetime_desimplify(self, value):
        result = datetime.datetime.strptime(value["value"], '%b %d %Y %H:%M:%S')
        if value["timezone"] == "UTC":
            result = pytz.utc.localize(result)
        return result

    def ipnetwork_desimplify(self, value):
        return netaddr.IPNetwork(value["value"])

    def desimplify(self, obj):

        result = obj

        if self.is_dict_and_has_key(obj, "simplify_strategy"):
            if obj['simplify_strategy'] == 'datetime':
                result = self.datetime_desimplify(obj)
            if obj['simplify_strategy'] == 'ipnetwork':
                result = self.ipnetwork_desimplify(obj)
            if obj['simplify_strategy'] == 'novabase':
                result = self.novabase_desimplify(obj)

        elif isinstance(obj, list):
            list_result = []

            for item in obj:
                list_result += [self.desimplify(item)]
            result = list_result
        elif isinstance(obj, dict) and obj.has_key("novabase_classname"):
            result = self.update_nova_model(obj)
        elif isinstance(obj, dict) and obj.has_key("metadata_novabase_classname"):
            result = self.update_nova_model(obj)


        """ Update foreign keys """
        self.update_foreign_keys(result)

        # print("desimplify(%s) -> %s" % (obj, result))
        return result