from django.db.backends import BaseDatabaseOperations
from pymongo.objectid import ObjectId

class DatabaseOperations(BaseDatabaseOperations):
    compiler_module = 'mongodj.db.compiler'

    def quote_name(self, name):
        return name

    def value_to_db_date(self, value):
        # TODO - take a look at date queries
        # value is a date here, no need to check it
        return value

    def sql_flush(self, style, tables, sequence_list):
        # TODO - flush the table
        return []

    def value_to_db_datetime(self, value):
        # value is a datetime here, no need to check it
        return value

    def value_to_db_time(self, value):
        # value is a time here, no need to check it
        return value

    def prep_for_like_query(self, value):
        return value

    def check_aggregate_support(self, aggregate):
        """
        This function is meant to raise exception if backend does
        not support aggregation.
        
        In fact, mongo probably even has more flexible aggregation
        support than relational DB
        """
        pass