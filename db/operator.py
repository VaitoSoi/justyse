import sqlmodel
import collections.abc as types

import utils

is_sql = utils.config.store_place.startswith("sql:")


def and_(*clauses):
    if is_sql:
        return sqlmodel.and_(*clauses)
    return all(clauses)


def or_(*clauses):
    if is_sql:
        return sqlmodel.or_(*clauses)
    return any(clauses)


def in_(field, values: types.Iterable):
    if isinstance(field, sqlmodel.Column):
        return field.in_(values)
    return field in values


def contain(field, value):
    if isinstance(field, sqlmodel.Column):
        return field.contains(value)
    return value in field
