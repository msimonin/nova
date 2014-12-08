
# RIAK
import riak

from models import get_model_class_from_name
import time
import traceback

dbClient = riak.RiakClient(pb_port=8087, protocol='pbc')

def now_in_ms():
    return int(round(time.time() * 1000))

class EmptyObject:
    pass

class LazyReference:

    lazy_ref_map = {}

    def convert_to_camelcase(word):
        return ''.join(x.capitalize() or '_' for x in word.split('_'))

    def __init__(self, base, id):
        self._base = base
        self._id = id

    def lazy_ref_key(self):
        return "%s_%s" % (self._base, str(self._id))

    def load(self):

        key = self.lazy_ref_key()
        current_ref = self.lazy_ref_map[key][1]

        key_index_bucket = dbClient.bucket(self._base)
        fetched = key_index_bucket.get(str(self._id))
        riak_object = fetched.data

        from desimplifier import ObjectDesimplifier

        desimplifier = ObjectDesimplifier()
        print(fetched.data)
        for key in riak_object:
            value = desimplifier.desimplify(riak_object[key])
            try:
                setattr(current_ref, key, desimplifier.desimplify(riak_object[key]))
            except Exception as e:
                pass

        self.update_relationships(current_ref)

    def find_object_with_filter(self, table_name, field_name, filtering_value):

        key_index_bucket = dbClient.bucket("key_index")
        fetched = key_index_bucket.get(table_name)
        keys = fetched.data

        result = []
        if keys != None:
            for key in keys:
                try:

                    key_as_string = str(key)

                    object_bucket_1 = dbClient.bucket(table_name)
                    riak_value = object_bucket_1.get(str(key)).data

                    if riak_value[field_name] == filtering_value:
                        model_object = LazyReference(table_name, str(key))
                        result += [model_object]

                except Exception as ex:
                    print("problem with key: %s" %(key))
                    traceback.print_exc()
                    pass
        
        if len(result) > 0:
            return result[0]
        return None


    def update_relationships(self, obj):

        skip_relationships = True
        relationships = None
        for field in obj._sa_class_manager:
            try:
                relationships = obj._sa_class_manager[field].parent.relationships._data
                skip_relationships = False
            except:
                pass
            break

        if not skip_relationships:
            
            for relationship in relationships:
                relationship_object = relationships[relationship]

                if "MANYTOONE" in str(relationship_object.direction):
                    for local_column_pair in relationship_object.local_remote_pairs:

                        local_column = local_column_pair[0]
                        remote_column = local_column_pair[1]

                        local_column_key = local_column.description
                        local_column_value = getattr(obj, local_column_key)


                        local_column_obj = str(relationship_object.class_attribute).split(".")[-1]

                        remote_column_key = remote_column.description
                        remote_table_name = str(remote_column.table)
                        remote_column_value = getattr(obj, local_column_obj)

                        if local_column_value is None and remote_column_value is None:
                            pass

                        if not local_column_value is None and not remote_column_value is None:
                            pass

                        if not local_column_value is None and remote_column_value is None:
                            remote_object = self.find_object_with_filter(remote_table_name, remote_column_key, local_column_value)
                            setattr(obj, local_column_obj, remote_object)
                            pass

                        if local_column_value is None and not remote_column_value is None:
                            pass

    def need_to_reload(self, key):

        need_to_reload = True

        if self.lazy_ref_map.has_key(key):
            return False

        return need_to_reload


    def get_complex_ref(self):

        key = self.lazy_ref_key()       

        if self.need_to_reload(key):

            model_class_name = self._base
            model_class_name = "".join([x.capitalize() for x in model_class_name.split("_")])

            model = get_model_class_from_name(model_class_name)

            if model is not None:
                self.lazy_ref_map[key] = (now_in_ms(), model())
            else:
                self.lazy_ref_map[key] = (now_in_ms(), EmptyObject())

            self.load()

        return self.lazy_ref_map[key][1]


    def __getattr__(self, item):
        return getattr(self.get_complex_ref(), item)

    def __str__(self):
        return "Lazy(%s)" % (self.lazy_ref_key())

    def __repr__(self):
        return "Lazy(%s)" % (self.lazy_ref_key())

    def __nonzero__(self):
        return not not self.get_complex_ref()
