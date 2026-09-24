import uuid

from pydantic import ConfigDict, Field

from src.utils.timestamped_model import TalkoTimestampedModel


class TalkoAssetsModel(TalkoTimestampedModel):
    """
    Represents a digital asset in the database.

    Attributes:
        unique_id (str): A unique identifier (UUID) for the digital asset.
        partner_id (int): The ID of the partner associated with the asset.
        version (int): The version number of the digital asset.
        asset_type (TalkoDigitalAssetEnum): The type of the asset, determined by the `TalkoDigitalAssetEnum` enum.
        additional_info (dict, optional): Metadata or additional properties associated with the asset.
        created_by (int, optional): The ID of the user who created the asset.
        updated_by (int, optional): The ID of the user who last updated the asset.
        created_at (int): The timestamp (in milliseconds) when the asset was created, defaulting to the current UTC time.
        updated_at (int): The timestamp (in milliseconds) when the asset was last updated, automatically updated on modification.

    Methods:
        __repr__: Returns a string representation of the DigitalAsset instance, including key attributes like `unique_id`, `asset_type`, and `version`.
    """

    name: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="FilePath for the asset",
    )
    partner_id: int
    version: int
    asset_type: str
    additional_info: dict | None = None
    created_by: int | None = None
    updated_by: int | None = None

    class CollectionName:
        ASSETS = "assets"  # Collection name

    model_config: ConfigDict = ConfigDict(arbitrary_types_allowed=True)
