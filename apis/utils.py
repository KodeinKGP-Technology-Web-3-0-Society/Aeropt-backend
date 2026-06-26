from rest_framework.response import Response


def success_response(data, status=200):
    return Response({"success": True, "data": data, "errors": None}, status=status)


def error_response(errors, status=400):
    return Response({"success": False, "data": None, "errors": errors}, status=status)


def custom_exception_handler(exc, context):
    from rest_framework.views import exception_handler

    response = exception_handler(exc, context)
    if response is None:
        return response

    errors = []
    if isinstance(response.data, dict):
        for field, messages in response.data.items():
            if isinstance(messages, list):
                for message in messages:
                    errors.append({"field": field, "message": str(message)})
            else:
                errors.append({"field": field, "message": str(messages)})
    elif isinstance(response.data, list):
        for message in response.data:
            errors.append({"field": "non_field_errors", "message": str(message)})
    else:
        errors.append({"field": "non_field_errors", "message": str(response.data)})

    response.data = {"success": False, "data": None, "errors": errors}
    return response
