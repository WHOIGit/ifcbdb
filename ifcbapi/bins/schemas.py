from ninja import Schema


class BinCriteriaSchema(Schema):
    dataset: str = None
    instrument: int = None


class BinSchema(Schema):
    pid: str
