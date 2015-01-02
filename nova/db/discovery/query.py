# Copyright (c) 2011 X.commerce, a business unit of eBay Inc.
# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Implementation of Discovery backend."""

import datetime

# RIAK
import riak
from nova.db.discovery.utils import get_objects
from nova.db.discovery.utils import is_novabase
from nova.db.discovery.utils import find_table_name
import itertools
import traceback
import inspect
from sqlalchemy.util._collections import KeyedTuple
from sqlalchemy.sql.expression import BinaryExpression
import pytz
try:
    from desimplifier import ObjectDesimplifier
    from desimplifier import find_table_name
except:
    pass
import collections
import uuid

dbClient = riak.RiakClient(pb_port=8087, protocol='pbc')

class Selection:
    def __init__(self, model, attributes, is_function=False, function=None, is_hidden=False):
        self._model = model
        self._attributes = attributes
        self._function = function
        self._is_function = is_function
        self.is_hidden = is_hidden

    def __str__(self):
        return "Selection(%s.%s)" % (self._model, self._attributes)

    def __unicode__(self):
        return self.__str__()
        
    def __repr__(self):
        return self.__str__()

class Function:

    def collect_field(self, rows, field):
        if rows is None:
            rows = []
        if "." in field:
            field = field.split(".")[1]
        result = [ getattr(row, field) for row in rows]
        return result

    def count(self, rows):
        collected_field_values = self.collect_field(rows, self._field)
        return len(collected_field_values)

    def sum(self, rows):
        result = 0
        collected_field_values = self.collect_field(rows, self._field)
        try:
            result = sum(collected_field_values)
        except:
            pass
        return result



    def __init__(self, name, field):
        self._name = name
        if name == "count":
            self._function = self.count
        elif name == "sum":
            self._function = self.sum
        else:
            self._function = self.sum
        self._field = field


import re

def extract_models(l):
    already_processed = set()
    result = []
    for selectable in [x for x in l if not x._is_function]:
        if not selectable._model in already_processed:
            already_processed.add(selectable._model)
            result += [selectable]
    return result


class RiakModelQuery:

    _funcs = []
    _initial_models = []
    _models = []
    _criterions = []

    def all_selectable_are_functions(self):
        return all(x._is_function for x in [y for y in self._models if not y.is_hidden])

    def __init__(self, *args, **kwargs):
        self._models = []
        self._criterions = []
        self._funcs = []

        base_model = None
        if kwargs.has_key("base_model"):
            base_model = kwargs.get("base_model")
        for arg in args:
            if "count" in str(arg) or "sum" in str(arg):
                function_name = re.sub("\(.*\)", "", str(arg))
                field_id = re.sub("\)", "", re.sub(".*\(", "", str(arg)))
                self._models += [Selection(None, None, is_function=True, function=Function(function_name, field_id))]
            elif self.find_table_name(arg) != "none":
                arg_as_text = "%s" % (arg)
                attribute_name = "*"
                if not hasattr(arg, "_sa_class_manager"):
                    if(len(arg_as_text.split(".")) > 1):
                        attribute_name = arg_as_text.split(".")[-1]
                    if hasattr(arg, "_sa_class_manager"):
                        self._models += [Selection(arg, attribute_name)]
                    elif hasattr(arg, "class_"):
                        self._models += [Selection(arg.class_, attribute_name)]
                else:
                    self._models += [Selection(arg, "*")]
                    pass
            elif isinstance(arg, Selection):
                self._models += [arg]
            elif isinstance(arg, Function):
                self._models += [Selection(None, None, True, arg)]
                self._funcs += [arg]
            elif isinstance(arg, BinaryExpression):
                self._criterions += [arg]
            else:
                pass


        if self.all_selectable_are_functions():
            if base_model:
                self._models += [Selection(base_model, "*", is_hidden=True)]

    def find_table_name(self, model):

        """This function return the name of the given model as a String. If the
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

    def construct_rows(self):

        """This function constructs the rows that corresponds to the current query.
        :return: a list of row, according to sqlalchemy expectation
        """

        def extract_sub_row(row, selectables):

            """Adapt a row result to the expectation of sqlalchemy.
            :param row: a list of python objects
            :param selectables: a list entity class
            :return: the response follows what is required by sqlalchemy (if len(model)==1, a single object is fine, in
            the other case, a KeyTuple where each sub object is associated with it's entity name
            """

            if len(selectables) > 1:

                labels = []

                for selectable in selectables:
                    labels += [self.find_table_name(selectable._model).capitalize()]

                product = []
                for label in labels:
                    product = product + [getattr(row, label)]

                # Updating Foreign Keys of objects that are in the row
                for label in labels:
                    current_object = getattr(row, label)
                    metadata = current_object.metadata
                    if metadata and hasattr(metadata, "_fk_memos"):
                        for fk_name in metadata._fk_memos:
                            fks = metadata._fk_memos[fk_name]
                            for fk in fks:
                                local_field_name = fk.column._label
                                remote_table_name = fk._colspec.split(".")[-2].capitalize()
                                remote_field_name = fk._colspec.split(".")[-1]

                                try:
                                    remote_object = getattr(row, remote_table_name)
                                    remote_field_value = getattr(remote_object, remote_field_name)
                                    setattr(current_object, local_field_name, remote_field_value)
                                except:
                                    pass

                # Updating fields that are setted to None and that have default values
                for label in labels:
                    current_object = getattr(row, label)
                    for field in current_object._sa_class_manager:
                        instance_state = current_object._sa_instance_state
                        field_value = getattr(current_object, field)
                        if field_value is None:
                            try:
                                field_column = instance_state.mapper._props[field].columns[0]
                                field_default_value = field_column.default.arg
                                setattr(current_object, field, field_default_value)
                            except:
                                pass

                return KeyedTuple(product, labels=labels)
            else:
                model_name = self.find_table_name(selectables[0]._model).capitalize()
                return getattr(row, model_name)


        request_uuid = uuid.uuid1()

        labels = []
        columns = set([])
        rows = []

        model_set = extract_models(self._models)

        # get the fields of the join result
        for selectable in model_set:
            labels += [self.find_table_name(selectable._model).capitalize()]

            if selectable._attributes == "*":
                try:
                    selected_attributes = selectable._model._sa_class_manager
                except:
                    selected_attributes = selectable._model.class_._sa_class_manager
                    pass
            else:
                selected_attributes = [selectable._attributes]

            for field in selected_attributes:

                attribute = None
                if hasattr(self._models, "class_"):
                    attribute = selectable._model.class_._sa_class_manager[field].__str__()
                elif hasattr(self._models, "_sa_class_manager"):
                    attribute = selectable._model._sa_class_manager[field].__str__()

                if attribute is not None:
                    columns.add(attribute)

        # construct the cartesian product
        list_results = []
        for selectable in model_set:
            tablename = find_table_name(selectable._model)
            objects = get_objects(tablename, request_uuid=request_uuid)
            list_results += [objects]

        # construct the cartesian product
        cartesian_product = []
        for element in itertools.product(*list_results):
            cartesian_product += [element]

        # filter elements of the cartesian product
        for product in cartesian_product:
            if len(product) > 0:
                row = KeyedTuple(product, labels=labels)
                all_criterions_satisfied = True

                for criterion in self._criterions:
                    if not self.evaluate_criterion(criterion, row):
                        all_criterions_satisfied = False
                if all_criterions_satisfied and not row in rows:
                    rows += [extract_sub_row(row, model_set)]

        final_rows = []
        showable_selection = [x for x in self._models if (not x.is_hidden) or x._is_function]

        if self.all_selectable_are_functions():
            final_row = []
            for selection in showable_selection:
                value = selection._function._function(rows)
                final_row += [value]
            return [final_row]
        else:
            for row in rows:
                final_row = []
                for selection in showable_selection:
                    if selection._is_function:
                        value = selection._function._function(rows)
                        final_row += [value]
                    else:
                        current_table_name = self.find_table_name(selection._model)
                        key = current_table_name.capitalize()
                        value = None
                        if not is_novabase(row) and hasattr(row, key):
                            value = getattr(row, key)
                        else:
                            value = row
                        if value is not None:
                            if selection._attributes != "*":
                                final_row += [getattr(value, selection._attributes)]
                            else:
                                final_row += [value]
                if len(showable_selection) == 1:
                    final_rows += final_row
                else:
                    final_rows += [final_row]

        return final_rows


    def evaluate_criterion(self, criterion, value):

        def uncapitalize(s):
            return s[:1].lower() + s[1:] if s else ''

        def getattr_rec(obj, attr, otherwise=None):
            """ A reccursive getattr function.

            :param obj: the object that will be use to perform the search
            :param attr: the searched attribute
            :param otherwise: value returned in case attr was not found
            :return:
            """
            try:
                if not "." in attr:
                    return getattr(obj, attr)
                else:
                    current_key = attr[:attr.index(".")]
                    next_key = attr[attr.index(".") + 1:]
                    if hasattr(obj, current_key):
                        current_object = getattr(obj, current_key)
                    elif hasattr(obj, current_key.capitalize()):
                        current_object = getattr(obj, current_key.capitalize())
                    elif hasattr(obj, uncapitalize(current_key)):
                        current_object = getattr(obj, uncapitalize(current_key))
                    else:                        
                        current_object = getattr(obj, current_key)

                    return getattr_rec(current_object, next_key, otherwise)
            except AttributeError:
                    return otherwise

        criterion_str = criterion.__str__()

        if "=" in criterion_str:
            def comparator (a, b):
                if a is None or b is None:
                    return False
                return "%s" %(a) == "%s" %(b)
            op = "="

        if "IS" in criterion_str:
            def comparator (a, b):
                if a is None or b is None:
                    if a is None and b is None:
                        return True
                    else:
                        return False
                return a is b
            op = "IS"

        if "!=" in criterion_str:
            def comparator (a, b):
                if a is None or b is None:
                    return False
                return a is not b
            op = "!="

        if "<" in criterion_str:
            def comparator (a, b):
                if a is None or b is None:
                    return False
                return a < b
            op = "<"

        if ">" in criterion_str:
            def comparator (a, b):
                if a is None or b is None:
                    return False
                return a > b
            op = ">"

        if "IN" in criterion_str:
            def comparator (a, b):
                if a is None or b is None:
                    return False
                return a == b
            op = "IN"

        split = criterion_str.split(op)
        left = split[0].strip()
        right = split[1].strip()
        left_values = []

        # Computing left value
        if left.startswith(":"):
            left_values += [criterion._orig[0].effective_value]
        else:
            left_values += [getattr_rec(value, left.capitalize())]


        # Computing right value
        if right.startswith(":"):
            right_value = criterion._orig[1].effective_value
        else:
            if isinstance(criterion._orig[1], bool):
                right_value = criterion._orig[1]
            else:
                right_type_name = "none"
                try:
                    right_type_name = str(criterion._orig[1].type)
                except:
                    pass

                if right_type_name == "BOOLEAN":
                    right_value = right
                    if right_value == "1":
                        right_value = True
                    else:
                        right_value = False
                else:
                    right_value = getattr_rec(value, right.capitalize())

        # try:
        #     print(">>> (%s)[%s] = %s <-> %s" % (value.keys(), left, left_values, right))
        # except:
        #     pass

        result = False
        for left_value in left_values:
                
            if isinstance(left_value, datetime.datetime):
                if left_value.tzinfo is None:
                    left_value = pytz.utc.localize(left_value)

            if isinstance(right_value, datetime.datetime):
                if right_value.tzinfo is None:
                    right_value = pytz.utc.localize(right_value)

            if "NOT NULL" in right:
                if left_value is not None:
                    result = True
            else:
                if comparator(left_value, right_value):
                    result = True

        if op == "IN":
            result = False
            right_terms = set(criterion.right.element)

            if left_value is None and hasattr(value, "__iter__"):
                left_key = left.split(".")[-1]
                if value[0].has_key(left_key):
                    left_value = value[0][left_key]

            for right_term in right_terms:
                try:
                    right_value = getattr(right_term.value, "%s" % (right_term._orig_key))
                except AttributeError:
                    right_value = right_term.value
                
                if isinstance(left_value, datetime.datetime):
                    if left_value.tzinfo is None:
                        left_value = pytz.utc.localize(left_value)

                if isinstance(right_value, datetime.datetime):
                    if right_value.tzinfo is None:
                        right_value = pytz.utc.localize(right_value)

                if comparator(left_value, right_value):
                    result = True

        return result

    def all(self):

        result_list = self.construct_rows()

        result = []
        for r in result_list:
            ok = True

            if ok:
                result += [r]
        return result

    def first(self):
        rows = self.all()
        if len(rows) > 0:
            return rows[0]
        else:
            None

    def exists(self):
        return self.first() is not None

    def count(self):
        return len(self.all())

    def soft_delete(self, synchronize_session=False):
        return self

    def update(self, values, synchronize_session='evaluate'):

        try:
            from desimplifier import ObjectDesimplifier
        except:
            pass
            
        rows = self.all()
        for row in rows:
            tablename = self.find_table_name(row)
            id = row.id

            print("[DEBUG-UPDATE] I shall update %s@%s with %s" % (str(id), tablename, values))

            object_bucket = dbClient.bucket(tablename)

            key_as_string = "%d" % (id)
            data = object_bucket.get(key_as_string).data

            for key in values:
                data[key] = values[key]

            request_uuid = uuid.uuid1()
            object_desimplifier = ObjectDesimplifier(request_uuid=request_uuid)
            
            try:
                desimplified_object = object_desimplifier.desimplify(data)
                desimplified_object.save()
            except Exception as e:
                traceback.print_exc()
                print("[DEBUG-UPDATE] could not save %s@%s" % (str(id), tablename))
                return None

        return len(rows)

    ####################################################################################################################
    # Query construction
    ####################################################################################################################

    def filter_by(self, **kwargs):
        _func = self._funcs[:]
        _criterions = self._criterions[:]
        for a in kwargs:
            for selectable in self._models:
                try:
                    column = getattr(selectable._model, a)
                    _criterions += [column.__eq__(kwargs[a])]
                    break
                except Exception as e:
                    # create a binary expression
                    traceback.print_exc()
        args = self._models + _func + _criterions + self._initial_models
        return RiakModelQuery(*args)

    # criterions can be a function
    def filter(self, *criterions):
        _func = self._funcs[:]
        _criterions = self._criterions[:]
        for criterion in criterions:
            _criterions += [criterion]
        args = self._models + _func + _criterions + self._initial_models
        return RiakModelQuery(*args)

    def join(self, *args, **kwargs):
        _func = self._funcs[:]
        _models = self._models[:]
        _criterions = self._criterions[:]
        for arg in args:

            if not isinstance(arg, list) and not isinstance(arg, tuple):
               tuples = [arg]
            else:
                tuples = arg

            for item in tuples:
                is_class = inspect.isclass(item)
                is_expression = isinstance(item, BinaryExpression)
                if is_class:
                    _models = _models + [Selection(item, "*")]
                elif is_expression:
                    _criterions += [item]
                else:
                    pass
        args = _models + _func + _criterions + self._initial_models
        return RiakModelQuery(*args)

    def outerjoin(self, *args, **kwargs):
        return self.join(*args, **kwargs)

    def options(self, *args):
        _func = self._funcs[:]
        _models = self._models[:]
        _criterions = self._criterions[:]
        _initial_models = self._initial_models[:]
        args = _models + _func + _criterions + _initial_models
        return RiakModelQuery(*args)

    def order_by(self, *criterion):
        _func = self._funcs[:]
        _models = self._models[:]
        _criterions = self._criterions[:]
        _initial_models = self._initial_models[:]
        args = _models + _func + _criterions + _initial_models
        return RiakModelQuery(*args)

    def with_lockmode(self, mode):
        return self


    def subquery(self):
        _func = self._funcs[:]
        _models = self._models[:]
        _criterions = self._criterions[:]
        _initial_models = self._initial_models[:]
        args = _models + _func + _criterions + _initial_models
        return RiakModelQuery(*args).all()

    def __iter__(self):
        return iter(self.all())
