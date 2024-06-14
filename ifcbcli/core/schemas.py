from pydantic import BaseModel


class DatasetSchema(BaseModel):
    id: int
    name: str
    title: str


class TagSchema(BaseModel):
    name: str


class BinCriteriaSchema(BaseModel):
    dataset: str = None


class BinSchema(BaseModel):
    pid: str
