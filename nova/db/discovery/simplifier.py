"""Simplifier module.

This module contains functions, classes and mix-in that are used for the
simplifcation of objects, before storing them into the discovery database.

"""

import models
import traceback

from utils import merge_dicts

def extract_adress(obj):
    """Extract an indentifier for the given object: if the object contains an
    id, it returns the id, otherwise it returns the memory address of the
    given object."""

    result = hex(id(obj))
    try:
        if isinstance(obj, NovaBase):
            result = str(obj).split("at ")[1].split(">")[0]
    except:
        pass
    return result

class RelationshipIdentifier(object):
    """An object that represent information about relationship between a class
    and a remote class."""

    def __init__(self, tablename, field_name, field_id):
        self._tablename = tablename
        self._field_name = field_name
        self._field_id = field_id

class ObjectSimplifier(object):
    """A class that is in charge of converting python objects (basic types,
    dictionnaries, novabase objects, ...) to a representation that can
    be stored in database."""

    simple_cache = {}
    complex_cache = {}

    def __init__(self):
        self.reset()

    def get_cache_key(self, obj):
        """Compute an "unique" key for the given object: this key is used to
        when caching objects."""

        classname = obj.__class__.__name__
        if classname == "LazyReference":
            return obj.lazy_ref_key()

        if hasattr(obj, "id") and getattr(obj, "id") is not None:
            key = "%s_%s" % (classname, obj.id)
        else:
            key = "%s_x%s" % (classname, extract_adress(obj))
        return key

    def already_processed(self, obj):
        """Check if the given object has been processed, according to its
        unique key."""

        key = self.get_cache_key(obj)
        return self.simple_cache.has_key(key)

    def datetime_simplify(self, datetime_ref):
        """Simplify a datetime object."""

        return {
            "simplify_strategy": "datetime",
            "value": datetime_ref.strftime('%b %d %Y %H:%M:%S'),
            "timezone" : str(datetime_ref.tzinfo)
        }

    def ipnetwork_simplify(self, ipnetwork):
        """Simplify an IP address object."""

        return {
            "simplify_strategy": "ipnetwork",
            "value": str(ipnetwork)
        }

    def novabase_simplify(self, obj, skip_complex_processing=False):
        """Simplify a NovaBase object."""

        if not self.already_processed(obj):

            def process_field(field_value):
                """Inner function that processes a value."""
                if not self.already_processed(field_value):
                    self.process_object(field_value, False)

                key = self.get_cache_key(obj)
                return self.simple_cache[key]


            obj.update_foreign_keys()
            key = self.get_cache_key(obj)

            if self.simple_cache.has_key(key):
                simplified_object = self.simple_cache[key]
            else:
                novabase_classname = str(obj.__class__.__name__)
                if isinstance(obj, dict) and "novabase_classname" in obj:
                    novabase_classname = obj["novabase_classname"]
                tmp = {
                    "simplify_strategy": "novabase",
                    "tablename": obj.__tablename__,
                    "novabase_classname": novabase_classname,
                    "id": obj.id,
                    "pid": extract_adress(obj)
                }
                if hasattr(tmp, "user_id"):
                    tmp = merge_dicts(obj, {"user_id": obj.user_id})
                if hasattr(tmp, "project_id"):
                    tmp = merge_dicts(tmp, {"project_id": obj.project_id})
                if not key in self.simple_cache:
                    self.simple_cache[key] = tmp

                simplified_object = tmp

            if skip_complex_processing:
                return simplified_object

            key = self.get_cache_key(obj)
            if not key in self.simple_cache:
                self.simple_cache[key] = simplified_object


            fields_to_iterate = None
            if hasattr(obj, "_sa_class_manager"):
                fields_to_iterate = obj._sa_class_manager
            elif hasattr(obj, "__dict__"):
                fields_to_iterate = obj.__dict__
            elif obj.__class__.__name__ == "dict":
                fields_to_iterate = obj


            complex_object = {}
            if fields_to_iterate is not None:
                for field in fields_to_iterate:
                    field_value = getattr(obj, field)

                    if isinstance(field_value, models.NovaBase):
                        complex_object[field] = process_field(field_value)
                    elif isinstance(field_value, list):
                        field_list = []
                        for item in field_value:
                            field_list += [process_field(item)]
                        complex_object[field] = field_list
                    else:
                        complex_object[field] = field_value

            metadata_class_name = novabase_classname
            complex_object["metadata_novabase_classname"] = metadata_class_name

            if not key in self.complex_cache:
                self.complex_cache[key] = complex_object
        else:
            key = self.get_cache_key(obj)
            simplified_object = self.simple_cache[key]
        return simplified_object

    def object_simplify(self, obj):
        """Convert this object to dictionnary that contains simplified values:
        every value is simplified according to the appropriate strategy."""

        result = obj
        do_deep_simplification = False
        is_basic_type = False

        try:
            if hasattr(obj, "__dict__") or obj.__class__.__name__ == "dict":
                do_deep_simplification = True
        except:
            is_basic_type = True

        if do_deep_simplification and not is_basic_type:
            fields = {}

            novabase_classname = str(obj.__class__.__name__)
            if isinstance(obj, dict) and "novabase_classname" in obj:
                novabase_classname = obj["novabase_classname"]

            # TODO(Jonathan): find a way to remove this hack
            if str(obj.__class__.__name__) != "dict":
                fields["novabase_classname"] = novabase_classname

            # Initialize fields to iterate
            dictionnary_object = {}
            if hasattr(obj, "__dict__"):
                dictionnary_object = obj.__dict__
            if obj.__class__.__name__ == "dict":
                dictionnary_object = obj

            if hasattr(obj, "reload_default_values"):
                obj.reload_default_values()

            if hasattr(obj, "reload_foreign_keys"):
                obj.reload_foreign_keys()

            # Prepare an Interator over obj's fields
            fields_iterator = {}
            if obj.__class__.__name__ == "dict":
                fields_iterator = dictionnary_object
            else:
                # Add table field in fields_to_iterate
                try:
                    for field in obj._sa_class_manager:
                        field_key = str(field)
                        field_object = obj._sa_class_manager[field]
                        is_relationship = "relationships" in str(field_object.comparator)
                        if is_relationship:
                            tablename = str(field_object.prop.table)
                            remote_name = field_object.prop._lazy_strategy.key
                            remote_id = next(iter(
                                field_object.prop._calculated_foreign_keys
                            )).key
                            fields_iterator[field] = RelationshipIdentifier(
                                tablename,
                                remote_name,
                                remote_id
                            )
                        else:
                            value = None
                            if dictionnary_object.has_key(field_key):
                                value = dictionnary_object[field_key]
                            fields_iterator[field_key] = value
                except Exception as e:
                    traceback.print_exc()

            # Process the fields and make reccursive calls
            if fields_iterator is not None:
                nova_fields = []
                for field in fields_iterator:
                    if not field.startswith('_') and field != 'metadata':
                        nova_fields.append(field)
                for field in nova_fields:
                    field_value = fields_iterator[field]

                    if isinstance(field_value, list):
                        copy_list = []
                        for item in field_value:
                            simple_value = self.process_object(item, True)
                            copy_list.append(simple_value)
                        fields[field] = copy_list
                    elif isinstance(field_value, RelationshipIdentifier):
                        fields[field] = self.relationship_simplify(
                            field_value,
                            getattr(obj, field_value._field_id)
                        )
                    else:
                        fields[field] = self.process_object(field_value, True)
                result = fields

            # Set default values
            # try:
            #     for field in obj._sa_class_manager:
            #         state = obj._sa_state
            #         field_value = getattr(obj, field)
            #         if field_value is None:
            #             try:
            #                 field_column = state.mapper._props[field].columns[0]
            #                 field_name = field_column.name
            #                 field_default_value = field_column.default.arg
            #                 if not "function" in str(type(field_default_value)):
            #                     fields[field_name] = field_default_value
            #             except:
            #                 pass
            # except:
            #     pass

            # # Updating Foreign Keys of objects that are in the row
            # try:
            #     for field in obj._sa_class_manager:
            #         state = obj._sa_instance_state
            #         field_value = getattr(obj, field)

            #         if not field_value is None:
            #             break

            #         try:
            #             field_column = state.mapper._props[field].columns[0]

            #             if not field_column.foreign_keys:
            #                 break

            #             for fk in field_column.foreign_keys:
            #                 local_field = str(fk.parent).split(".")[-1]
            #                 remote_table = fk._colspec.split(".")[-2]
            #                 remote_field = fk._colspec.split(".")[-1]
            #                 try:

            #                     remote_object = None
            #                     try:
            #                         remote_object = getattr(
            #                             obj,
            #                             remote_table
            #                         )
            #                     except:
            #                         try:
            #                             if remote_table[-1] == "s":
            #                                 remote_table = remote_table[:-1]
            #                                 remote_object = getattr(
            #                                     obj,
            #                                     remote_table
            #                                 )
            #                         except:
            #                             pass
            #                     remote_value = getattr(
            #                         remote_object,
            #                         remote_field
            #                     )
            #                     fields[local_field] = remote_value
            #                 except:
            #                     pass
            #         except:
            #             pass
            # except:
            #     pass

            if isinstance(obj, models.NovaBase):
                key = self.get_cache_key(obj)
                if not key in self.complex_cache:
                    self.complex_cache[key] = result
                    self.simple_cache[key] = self.novabase_simplify(obj, True)

                    metadata_class_name = novabase_classname
                    metadata_dict = {
                        "metadata_novabase_classname": metadata_class_name
                    }
                    self.complex_cache[key] = merge_dicts(
                        self.complex_cache[key],
                        metadata_dict
                    )
                    self.simple_cache[key] = merge_dicts(
                        self.simple_cache[key],
                        metadata_dict
                    )

        return result

    def relationship_simplify(self, relationship, id_value):
        """Simplify a Relationship object."""

        return {
            "simplify_strategy": "novabase",
            "tablename": relationship._tablename,
            "id": id_value,
            "value": id_value
        }

    def process_object(self, obj, skip_reccursive_call=True):
        """Apply the best simplification strategy to the given object."""

        is_instance_of_novabase = isinstance(obj, models.NovaBase)
        should_skip = self.already_processed(obj) or skip_reccursive_call

        if is_instance_of_novabase and should_skip:
            result = self.novabase_simplify(obj)
        elif obj.__class__.__name__ == "datetime":
            result = self.datetime_simplify(obj)
        elif obj.__class__.__name__ == "IPNetwork":
            result = self.ipnetwork_simplify(obj)
        else:
            result = self.object_simplify(obj)

        return result


    def reset(self):
        """Reset the caches of the current instance of Simplifier."""

        self.simple_cache = {}
        self.complex_cache = {}

    def simplify(self, obj):
        """Simplify the given object."""

        result = self.process_object(obj, False)
        return result
