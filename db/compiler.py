import datetime
import sys

import pymongo
from pymongo.objectid import ObjectId

from django.db.models.sql import aggregates as sqlaggregates
from django.db.models.sql.compiler import SQLCompiler
from django.db.models.sql import aggregates as sqlaggregates
from django.db.models.sql.constants import LOOKUP_SEP, MULTI, SINGLE
from django.db.models.sql.where import AND, OR
from django.db.utils import DatabaseError, IntegrityError
from django.utils.tree import Node

from django.conf import settings

TYPE_MAPPING = {
    "unicode":  lambda val: unicode(val),
    "int":      lambda val: int(val),
    "float":    lambda val: float(val),
    "bool":     lambda val: bool(val),
}

OPERATORS_MAP = {
    'exact':    lambda val: val,
    'gt':       lambda val: {"$gt": val},
    'gte':      lambda val: {"$gte": val},
    'lt':       lambda val: {"$lt": val},
    'lte':      lambda val: {"$lte": val},
    'in':       lambda val: {"$in": val}
}

def _get_mapping(db_type, value, mapping):
    # TODO - comments. lotsa comments
    if db_type in mapping:
        _func = mapping[db_type]
    elif db_type in TYPE_MAPPING:
        _func = TYPE_MAPPING[db_type]
    else:
        _func = lambda val: val
    # TODO - what if the data is represented as list on the python side?
    if isinstance(value, list):
        return map(_func, value)
    return _func(value)
    
def python2db(db_type, value):
    mapping = {
        # TODO - get rid of dirty dirty hack
        "objectid": lambda val: ObjectId(val),
    }
    return _get_mapping(db_type, value, mapping)
    
def db2python(db_type, value):
    mapping = {
        "objectid": lambda val: val,
    }
    return _get_mapping(db_type, value, mapping)
    
def _parse_constraint(where_child, connection):
    _constraint, lookup_type, _annotation, value = where_child
    (table_alias, column, db_type), value = _constraint.process(lookup_type, value, connection)
    if lookup_type not in ('in', 'range') and isinstance(value, (tuple, list)):
        # Django fields always return a list (see Field.get_db_prep_lookup)
        # except if get_db_prep_lookup got overridden by a subclass
        if len(value) > 1:
            # TODO... - when can we get here?
            raise Exception("blah!")
        if lookup_type == 'isnull':
            value = annotation
        else:
            value = value[0]
    return (lookup_type, table_alias, column, db_type, value)

class SQLCompiler(SQLCompiler):
    """
    A simple query: no joins, no distinct, etc.
    
    Internal attributes of interest:
        x connection - DatabaseWrapper instance
        x query - query object, which is to be
            executed
    """
    
    def __init__(self, *args, **kw):
        super(SQLCompiler, self).__init__(*args, **kw)
        self.cursor = self.connection._cursor
    
    """
    Private API
    """
    def _execute_aggregate_query(self, aggregates, result_type):
        if len(aggregates) == 1 and isinstance(aggregates[0], sqlaggregates.Count):
            count = self.get_count()
        if result_type is SINGLE:
            return [count]
        elif result_type is MULTI:
            return [[count]]
    
    def _get_query(self):
        # TODO - OR queries
        query = {}
        where = self.query.where
        if where.connector == OR:
            raise NotImplementedError("OR- queries not supported yet")
               
        for child in where.children:
            if isinstance(child, tuple):
                # only one level of hierarchy for now
                # TODO - proper way, but for now - since there are no joins "table_alias" should be the same as the table name
                
                lookup_type, collection, column, db_type, value = _parse_constraint(child, self.connection)
                query[column] = OPERATORS_MAP[lookup_type](python2db(db_type, value))
        
        return query
    
    def _get_collection(self):
        _collection = self.query.model._meta.db_table
        return self.cursor()[_collection]
        
    """
    Public API
    """
    def get_count(self):
        return self.get_results().count()
    
    def get_results(self):
        """
        @returns: pymongo iterator over results
        defined by self.query
        """
        _high_limit = self.query.high_mark or 0
        _low_limit = self.query.low_mark or 0

        return self._get_collection().find(self._get_query()).skip(_low_limit).limit(_high_limit - _low_limit)

    """
    API used by Django
    """
    def results_iter(self):
        """
        Returns an iterator over the results from executing this query.
        
        self.query - the query created by the ORM
        self.query.where - conditions imposed by the query
        """
        for document in self.get_results():
            result = []
            for field in self.query.get_meta().local_fields:
                result.append(db2python(field.db_type(
                    connection=self.connection), document.get(field.column, field.default)))
            yield result
            
    def execute_sql(self, result_type=MULTI):
        # let's catch aggregate call
        aggregates = self.query.aggregate_select.values()
        if aggregates:
            return self._execute_aggregate_query(aggregates, result_type)
        return
            
    def has_results(self):
        return self.get_count() > 0
                        
class SQLInsertCompiler(SQLCompiler):
    
    def execute_sql(self, return_id=False):
        """
        self.query - the data that should be inserted
        """
        dat = {}
        for (field, value), column in zip(self.query.values, self.query.columns):
            dat[column] = python2db(field.db_type(connection=self.connection), value)
        # every object should have a pk
        dat['id'] = str(ObjectId())
        self.connection._cursor()[self.query.get_meta().db_table].save(dat)

class SQLUpdateCompiler(SQLCompiler):
    # TODO
    pass

class SQLDeleteCompiler(SQLCompiler):
    def execute_sql(self, result_type=MULTI):
        return self._get_collection().remove(self._get_query())