from pydantic import BaseModel
from typing import Optional, List


class PersonEntry(BaseModel):
    name: str
    title: Optional[str] = None


class CompanyEntry(BaseModel):
    label: str
    firm_name: str
    people: List[PersonEntry] = []


class PipelineProject(BaseModel):
    name_or_address: str
    description: str


class KeyDataPoint(BaseModel):
    label: str
    value: str


class DataPoints(BaseModel):
    property_type: Optional[str] = None
    property_name: Optional[str] = None
    address: Optional[str] = None
    address_sourced_separately: bool = False
    size_sf: Optional[float] = None
    size_units: Optional[int] = None
    size_beds: Optional[int] = None
    size_keys: Optional[int] = None
    rental_rate: Optional[float] = None   # $/SF/year for leases
    sale_price: Optional[float] = None
    loan_amount: Optional[float] = None
    total_project_cost: Optional[float] = None
    occupancy: Optional[float] = None   # percentage e.g. 94.7
    year_built: Optional[int] = None
    completion: Optional[str] = None
    phase_1: Optional[str] = None
    total_project_all_phases: Optional[str] = None
    original_plan: Optional[str] = None
    land_area_acres: Optional[float] = None
    multi_asset_purchase: bool = False
    notable_features: Optional[str] = None
    project_notes: Optional[str] = None


class ArticleSummary(BaseModel):
    narrative: str
    transaction_type: Optional[str] = None   # for transaction articles
    article_type: Optional[str] = None        # for market/research articles
    market: Optional[str] = None
    data_points: Optional[DataPoints] = None
    key_data_points: List[KeyDataPoint] = []  # for market/research articles
    companies_people: List[CompanyEntry] = []
    tenants: List[str] = []
    financing: Optional[str] = None
    sponsor_pipeline: List[PipelineProject] = []
    market_intelligence: Optional[str] = None
