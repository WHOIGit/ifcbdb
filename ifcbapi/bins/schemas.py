from ninja import Schema


class BinCriteriaSchema(Schema):
    dataset: str = None


class BinSchema(Schema):
    pid: str
