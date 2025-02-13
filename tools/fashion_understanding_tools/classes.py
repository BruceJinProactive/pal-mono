from typing import List, Union

from pydantic import BaseModel


class FashionItem(BaseModel):
    item_name: str
    colors: Union[str, List[str]]
    occasions: Union[str, List[str]]
    categories: Union[str, List[str]]
    fit_features: List[str]


class ImageIdentification(BaseModel):
    image_of_interest: str
