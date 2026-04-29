from functools import wraps
from flask import request, jsonify
from pydantic import BaseModel, ValidationError


def validate_request(schema_cls: type[BaseModel]):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            data = request.get_json(silent=True)
            if data is None:
                return jsonify({"error": "request body must be JSON"}), 400
            try:
                model = schema_cls.model_validate(data)
            except ValidationError as e:
                details = [
                    {"field": ".".join(str(l) for l in err["loc"]), "message": err["msg"]}
                    for err in e.errors()
                ]
                return jsonify({"error": "validation failed", "details": details}), 422
            kwargs["body"] = model
            return fn(*args, **kwargs)
        return wrapper
    return decorator
