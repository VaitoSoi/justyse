import copy
import typing

import pydantic
import sqlmodel


def partial_model(model: sqlmodel.SQLModel):
    """
    Create a partial model from a pydantic.BaseModel
    From: https://stackoverflow.com/a/76560886/17106809
    """

    def make_field_optional(
            field: pydantic.fields.FieldInfo,
            default: typing.Any = None,
            default_factory: typing.Callable[[], typing.Any] = lambda: None,
    ) -> tuple[typing.Any, pydantic.fields.FieldInfo]:
        new = copy.deepcopy(field)
        new.default = default
        new.default_factory = default_factory
        new.annotation = typing.Optional[field.annotation]  # type: ignore
        return new.annotation, new

    return pydantic.create_model(
        model.__name__,
        __base__=sqlmodel.SQLModel,
        __module__=model.__module__,
        **{
            field_name: make_field_optional(field_info)
            for field_name, field_info in model.model_fields.items()
        },
    )
