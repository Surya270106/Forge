from pydantic import BaseModel, Field


class PluginManifest(BaseModel):
    id: str = Field(..., description="Unique identifier for the plugin")
    version: str = Field(..., description="SemVer version")
    name: str = Field(..., description="Human readable name")
    description: str = Field(..., description="Plugin description")
    capabilities: list[str] = Field(default_factory=list, description="List of capabilities (e.g. 'mcp', 'hooks')")
    entrypoint: str = Field(..., description="Execution entrypoint for the plugin container or script")
