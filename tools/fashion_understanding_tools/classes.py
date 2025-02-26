import json
import os
from enum import IntEnum
from typing import List, Union

from pydantic import BaseModel


##### classes for function calling #####
class CloseUpItem(BaseModel):
    index_of_item: int


class FashionItem(BaseModel):
    item_name: str
    colors: Union[str, List[str]]
    occasions: Union[str, List[str]]
    categories: Union[str, List[str]]
    fit_features: List[str]


class ImageIdentification(BaseModel):
    image_of_interest: str


class AntonymsofNegativeFashion(BaseModel):
    translated_fit_style: Union[List[str], None]


class PastImageIdentifier(BaseModel):
    index_of_item: int


class NegativeFashion(BaseModel):
    occasion: Union[List[str], None]
    category: Union[List[str], None]
    color: Union[List[str], None]
    material: Union[List[str], None]
    patterns: Union[List[str], None]
    disliked_fit_style: Union[List[str], None]
    aesthetics: Union[List[str], None]


#######################################
class ImageIdentificationOutput(IntEnum):
    """Enum class for image identification."""

    UPLOADED_IMAGE = 0
    RECOMMENDED_ITEMS = 1
    NO_IMAGE = 2


class GeneralFunctions(BaseModel):
    ### TODO: Discuss with the ENG team how to store the hierarchy information
    def get_hierarchy(self) -> dict:
        """
        Get the hierarchy information from the ENG team.
        """

        # Load fashion knowledge base hierarchy
        hierarchy_file = os.path.join(
            os.path.dirname(__file__), "labels/labels_v1.json"
        )
        hierarchy = json.load(open(hierarchy_file, "r"))

        # Convert all values to lowercase
        processed_hierarchy = {}

        for key, value in hierarchy.items():
            processed_hierarchy[key] = [v.lower() for v in value]

        return processed_hierarchy

    def _lowercase_keys(self, dictionary: dict) -> dict:
        """This function converts all keys in a dictionary to lowercase.

        Args:
            dictionary (dict): The dictionary to convert.

        Returns:
            A new dictionary with all keys converted to lowercase.
        """
        return {k.lower(): v for k, v in dictionary.items()}

    def _restrict_api_call_params(
        self, api_call_params: dict, hierarchy: dict, mapping=None
    ) -> dict:
        """Restrict the API call parameters to the allowed values.

        Args:
            api_call_params (dict): The API call parameters.
            hierarchy (dict): The fashion hierarchy values.
            mapping (dict): The mapping between the API call parameters and the hierarchy values. Optional.

        Returns:
            dict: The restricted API call parameters.
        """

        # Restrict the colors, occasions, and categories to the hierarchy values using the `enum` field
        for k in api_call_params["properties"]:
            # Decide whether to use the mapping
            if mapping is not None and k in mapping:
                hierarchy_k = mapping[k]
                if hierarchy_k in hierarchy:
                    api_call_params["properties"][k]["enum"] = hierarchy[hierarchy_k]
            else:
                if k in hierarchy:
                    api_call_params["properties"][k]["enum"] = hierarchy[k]

        return api_call_params
