from pydantic import BaseModel, HttpUrl, Field
from typing import Optional

class Company(BaseModel):
    url: HttpUrl = Field(description="The company's website url")
    name: Optional[str] = Field(default=None, description="The name of the company")
    description: Optional[str] = Field(default=None, description="Company description")
    source: Optional[str] = Field(default=None, description="The website where the data was extracted from")
    location: Optional[str] = Field(default=None, description="Where the company is located")
    domain: Optional[str] = Field(default=None, description="The domain in which the company is operating")