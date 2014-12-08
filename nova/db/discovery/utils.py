"""Utils module.

This module contains functions, classes and mix-in that are used for the
discovery database backend.

"""

from oslo.db.sqlalchemy import models

def merge_dicts(dict1, dict2):
    """Merge two dictionnaries into one dictionnary: the values containeds
    inside dict2 will erase values of dict1."""
    return dict(dict1.items() + dict2.items())

class ReloadableRelationMixin(models.ModelBase):
    """Mixin that contains several methods that will be in charge of enabling
    NovaBase instances to reload default values and relationships."""

    def reload_default_values(self):
        """Reload the default values of un-setted fields that."""

        for field in self._sa_class_manager:
            state = self._sa_instance_state
            field_value = getattr(self, field)
            if field_value is None:
                try:
                    field_column = state.mapper._props[field].columns[0]
                    field_name = field_column.name
                    field_default_value = field_column.default.arg
                    if not "function" in str(type(field_default_value)):
                        setattr(field_name, field_default_value)
                except:
                    pass

    def reload_foreign_keys(self):
        """Reload foreign keys."""
        
        try:
            for field in self._sa_class_manager:
                state = self._sa_instance_state
                field_value = getattr(self, field)

                if not field_value is None:
                    break

                try:
                    field_column = state.mapper._props[field].columns[0]

                    if not field_column.foreign_keys:
                        break

                    for fk in field_column.foreign_keys:
                        local_field = str(fk.parent).split(".")[-1]
                        remote_table = fk._colspec.split(".")[-2]
                        remote_field = fk._colspec.split(".")[-1]
                        try:

                            remote_object = None
                            try:
                                remote_object = getattr(
                                    self,
                                    remote_table
                                )
                            except:
                                try:
                                    if remote_table[-1] == "s":
                                        remote_table = remote_table[:-1]
                                        remote_object = getattr(
                                            self,
                                            remote_table
                                        )
                                except:
                                    pass
                            remote_value = getattr(
                                remote_object,
                                remote_field
                            )
                            setattr(self, local_field, remote_value)
                        except:
                            pass
                except:
                    pass
        except:
            pass
