from rest_framework.pagination import PageNumberPagination


class StandardResultsPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count":    {"type": "integer"},
                "next":     {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "results":  schema,
            },
        }
