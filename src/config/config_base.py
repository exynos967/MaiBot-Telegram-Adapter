from dataclasses import dataclass, fields, MISSING
from typing import TypeVar, Type, Any, get_origin, get_args, Literal, Dict, Union

T = TypeVar("T", bound="ConfigBase")


@dataclass
class ConfigBase:
    @classmethod
    def from_dict(cls: Type[T], data: Dict[str, Any]) -> T:
        if not isinstance(data, dict):
            raise TypeError(f"Expected dict, got {type(data).__name__}")

        init_args: Dict[str, Any] = {}
        for f in fields(cls):
            name = f.name
            if name.startswith("_"):
                continue
            if name not in data:
                if f.default is not MISSING or f.default_factory is not MISSING:
                    continue
                raise ValueError(f"Missing required field: {name}")
            value = data[name]
            init_args[name] = cls._convert_field(value, f.type)
        return cls(**init_args)  # type: ignore[arg-type]

    @classmethod
    def _convert_field(cls, value: Any, field_type: Any) -> Any:
        # dataclass nesting
        if isinstance(field_type, type) and issubclass(field_type, ConfigBase):
            return field_type.from_dict(value)

        origin = get_origin(field_type)
        args = get_args(field_type)

        if origin in {list, set, tuple}:
            if not isinstance(value, list):
                raise TypeError(f"Expected list for {field_type}")
            if origin is list:
                return [cls._convert_field(v, args[0]) for v in value]
            if origin is set:
                return {cls._convert_field(v, args[0]) for v in value}
            if origin is tuple:
                try:
                    return tuple(cls._convert_field(v, t) for v, t in zip(value, args, strict=True))
                except ValueError as e:
                    raise TypeError("Tuple length mismatch") from e

        if origin is dict:
            if not isinstance(value, dict):
                raise TypeError(f"Expected dict for {field_type}")
            kt, vt = args
            return {cls._convert_field(k, kt): cls._convert_field(v, vt) for k, v in value.items()}

        if origin is Union:
            if value is None:
                return None
            return cls._convert_field(value, args[0])

        if origin is Literal:
            allowed = get_args(field_type)
            if value in allowed:
                return value
            raise TypeError(f"Value {value} not in {allowed}")

        if origin is None:
            if isinstance(value, field_type):
                return field_type(value)
            raise TypeError(f"Expected {field_type.__name__}, got {type(value).__name__}")

        if field_type is Any:
            return value
        return field_type(value)
