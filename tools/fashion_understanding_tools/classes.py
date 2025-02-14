import json
import os
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

        return hierarchy

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
