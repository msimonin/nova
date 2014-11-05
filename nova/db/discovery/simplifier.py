
import models
import traceback

def extract_adress(obj):
    result = hex(id(obj))
    try:
        if isinstance(obj, NovaBase):
            result = str(obj).split("at ")[1].split(">")[0]
    except:
        pass
    return result

class RelationshipIdentifier:
    def __init__(self, tablename, field_name, field_id):
        self._tablename = tablename
        self._field_name = field_name
        self._field_id = field_id

class ObjectSimplifier():

    simplified_processed_objects = {}

    def __init__(self):
        self.reset()

    def already_processed(self, novabase_ref):
        key = "%s-%s" % (novabase_ref.__tablename__, novabase_ref.id)
        if novabase_ref.id == None:
            key = "%s-%s" % (novabase_ref.__tablename__, extract_adress(novabase_ref))
        return self.simplified_processed_objects.has_key(key)

    def datetime_simplify(self, datetime_ref):
        obj = {"simplify_strategy": "datetime", "value": datetime_ref.strftime('%b %d %Y %H:%M:%S'), "timezone" : str(datetime_ref.tzinfo)}
        return obj

    def ipnetwork_simplify(self, ipnetwork):
        obj = {"simplify_strategy": "ipnetwork", "value": str(ipnetwork)}
        return obj

    def _novabase_simplify(self, novabase_ref):
        novabase_ref.update_foreign_keys()
        key = "%s-%s" % (novabase_ref.__tablename__, novabase_ref.id)
        if novabase_ref.id == None:
            key = "%s-%s" % (novabase_ref.__tablename__, extract_adress(novabase_ref))
        if self.simplified_processed_objects.has_key(key):
            obj = self.simplified_processed_objects[key]
        else:
            # obj = {"simplify_strategy": "novabase", "tablename": novabase_ref.__tablename__, "id": novabase_ref.id, "value": novabase_ref}
            novabase_classname = str(novabase_ref.__class__.__name__)
            if isinstance(novabase_ref, dict) and "novabase_classname" in novabase_ref:
                novabase_classname = novabase_ref["novabase_classname"]
            obj = {"simplify_strategy": "novabase", "tablename": novabase_ref.__tablename__, "novabase_classname": str(novabase_ref.__class__.__name__) ,"id": novabase_ref.id, "pid": extract_adress(novabase_ref)}
            if hasattr(novabase_ref, "user_id"):
                obj["user_id"] = novabase_ref.user_id
            if hasattr(novabase_ref, "project_id"):
                obj["project_id"] = novabase_ref.project_id
            if not key in self.simplified_processed_objects:
                self.simplified_processed_objects[key] = obj
        return obj

    def relationship_simplify(self, relationship, id_value):
        obj = {"simplify_strategy": "novabase", "tablename": relationship._tablename, "id": id_value,
               "value": id_value}
        return obj

    def _simplify_current_object(self, obj, skip_reccursive_call=True):

        result = obj
        do_deep_simplification = False
        is_basic_type = False

        if isinstance(obj, models.NovaBase) and (self.already_processed(obj) or skip_reccursive_call):
            result = self.novabase_simplify(obj)
        elif obj.__class__.__name__ == "datetime":
            result = self.datetime_simplify(obj)
        elif obj.__class__.__name__ == "IPNetwork":
            result = self.ipnetwork_simplify(obj)
        else:
            try:
                if hasattr(obj, "__dict__") or obj.__class__.__name__ == "dict":
                    do_deep_simplification = True
            except:
                is_basic_type = True
                pass

            if do_deep_simplification and not is_basic_type:
                fields = {}

                # TODO: find a way to remove this hack
                if str(obj.__class__.__name__) != "dict":
                    fields["novabase_classname"] = str(obj.__class__.__name__)

                # Initialize fields to iterate
                dictionnary_object = {}
                if hasattr(obj, "__dict__"):
                    dictionnary_object = obj.__dict__
                if obj.__class__.__name__ == "dict":
                    dictionnary_object = obj
                
                fields_to_iterate = {}

                if obj.__class__.__name__ == "dict":
                    fields_to_iterate = dictionnary_object
                else:
                    # Add table field in fields_to_iterate
                    try:
                        for field in obj._sa_class_manager:
                            field_key = str(field)
                            field_object = obj._sa_class_manager[field]
                            is_relationship = "relationships" in str(field_object.comparator)
                            if is_relationship:
                                tablename = str(obj._sa_class_manager[field].prop.table)
                                local_field_name = obj._sa_class_manager[field].prop._lazy_strategy.key
                                local_field_id = next(iter(obj._sa_class_manager[field].prop._calculated_foreign_keys)).key
                                fields_to_iterate[str(field)] = RelationshipIdentifier(tablename, local_field_name, local_field_id)
                            else:
                                value = None
                                if dictionnary_object.has_key(field_key):
                                    value = dictionnary_object[field_key]
                                fields_to_iterate[field_key] = value
                    except Exception as e:
                        traceback.print_exc()
                        pass

                # # Add relations fields in fields_to_iterate
                # try:
                #     for field in obj._sa_class_manager:
                #         if not str(field) in fields_to_iterate:
                #             tablename = str(obj._sa_class_manager[field].prop.table)
                #             local_field_name = obj._sa_class_manager[field].prop._lazy_strategy.key
                #             local_field_id = next(iter(obj._sa_class_manager[field].prop._calculated_foreign_keys)).key
                #             fields_to_iterate[str(field)] = RelationshipIdentifier(tablename, local_field_name, local_field_id)
                # except:
                #     pass

                # Process the fields and make reccursive calls
                if fields_to_iterate is not None:
                    for field in [x for x in fields_to_iterate if not x.startswith('_') and x != 'metadata']:
                        field_value = fields_to_iterate[field]

                        if isinstance(field_value, list):
                            copy_list = []
                            for item in field_value:
                                copy_list += [self._simplify_current_object(item, True)]
                            fields[field] = copy_list
                        elif isinstance(field_value, RelationshipIdentifier):
                            fields[field] = self.relationship_simplify(field_value, getattr(obj, field_value._field_id))
                        else:
                            fields[field] = self._simplify_current_object(field_value, True)
                    result = fields

                """Set default values"""
                try:
                    for field in obj._sa_class_manager:
                        instance_state = obj._sa_instance_state
                        field_value = getattr(obj, field)
                        if field_value is None:
                            try:
                                field_column = instance_state.mapper._props[field].columns[0]
                                field_name = field_column.name
                                field_default_value = field_column.default.arg
                                # print(">>  fields[%s] <- %s" % (field_name, field_default_value))

                                if not "function" in str(type(field_default_value)):
                                    # print(">>2 fields[%s] <- %s" % (field_name, field_default_value))
                                    fields[field_name] = field_default_value
                            except:
                                pass
                except:
                    pass

                """Updating Foreign Keys of objects that are in the row"""
                try:
                    for field in obj._sa_class_manager:
                        instance_state = obj._sa_instance_state
                        field_value = getattr(obj, field)
                        if field_value is None:
                            try:
                                field_column = instance_state.mapper._props[field].columns[0]
                                if field_column.foreign_keys:
                                    for fk in field_column.foreign_keys:
                                        local_field_name = str(fk.parent).split(".")[-1]#column._label
                                        remote_table_name = fk._colspec.split(".")[-2]
                                        remote_field_name = fk._colspec.split(".")[-1]
                                        try:

                                            remote_object = None
                                            try:
                                                remote_object = getattr(obj, remote_table_name)
                                            except:
                                                try:
                                                    if remote_table_name[-1] == "s":
                                                        remote_table_name = remote_table_name[:-1]
                                                        remote_object = getattr(obj, remote_table_name)
                                                except:
                                                    pass
                                            remote_field_value = getattr(remote_object, remote_field_name)                                  
                                            fields[local_field_name] = remote_field_value
                                        except:
                                            pass
                            except:
                                pass
                except:
                    pass

                if isinstance(obj, models.NovaBase):
                    key = "%s-%s" % (obj.__tablename__, obj.id)
                    if obj.id == None:
                        key = "%s-%s" % (obj.__tablename__, extract_adress(novabase_ref))
                    if not key in self.complex_processed_objects:
                        self.complex_processed_objects[key] = result
                        self.simplified_processed_objects[key] = self._novabase_simplify(obj)

        return result


    def reset(self):

        self.simplified_processed_objects = {}
        self.complex_processed_objects = {}

    def already_processed_novabase(self, novabase_ref):
        return already_processed_novabase(self.simplified_processed_objects, novabase_ref)


    def novabase_simplify(self, novabase_ref):

        if not self.already_processed(novabase_ref):

            def process_field(field_value):
                if not self.already_processed(field_value):
                    self._simplify_current_object(field_value, False)

                key = "%s-%s" % (field_value.__tablename__, field_value.id)
                if field_value.id == None:
                    key = "%s-%s" % (field_value.__tablename__, extract_adress(novabase_ref))
                return self.simplified_processed_objects[key]


            simplified_object = self._novabase_simplify(novabase_ref)

            key = "%s-%s" % (novabase_ref.__tablename__, novabase_ref.id)
            if novabase_ref.id == None:
                key = "%s-%s" % (novabase_ref.__tablename__, extract_adress(novabase_ref))
            if not key in self.simplified_processed_objects:
                self.simplified_processed_objects[key] = simplified_object


            fields_to_iterate = None
            if hasattr(novabase_ref, "_sa_class_manager"):
                fields_to_iterate = novabase_ref._sa_class_manager
            elif hasattr(novabase_ref, "__dict__"):
                fields_to_iterate = novabase_ref.__dict__
            elif novabase_ref.__class__.__name__ == "dict":
                fields_to_iterate = novabase_ref


            complex_object = {}
            if fields_to_iterate is not None:
                for field in fields_to_iterate:
                    field_value = getattr(novabase_ref, field)

                    if isinstance(field_value, models.NovaBase):
                        complex_object[field] = process_field(field_value)
                    elif isinstance(field_value, list):
                        field_list = []
                        for item in field_value:
                            field_list += [process_field(item)]
                        complex_object[field] = field_list
                    else:
                        complex_object[field] = field_value

            # print(complex_object)
            if not key in self.complex_processed_objects:
                self.complex_processed_objects[key] = complex_object
            # self.simplify(novabase_ref)

        else:
            key = "%s-%s" % (novabase_ref.__tablename__, novabase_ref.id)
            if novabase_ref.id == None:
                key = "%s-%s" % (novabase_ref.__tablename__, extract_adress(novabase_ref))
            simplified_object = self.simplified_processed_objects[key]

        return simplified_object

    def simplify(self, obj):
        result = self._simplify_current_object(obj, False)
        return result
