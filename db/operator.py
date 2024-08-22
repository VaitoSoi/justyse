import sqlmodel

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
