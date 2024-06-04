from ninja import Schema


class DatasetSchema(Schema):
    id: int
    name: str
    title: str
