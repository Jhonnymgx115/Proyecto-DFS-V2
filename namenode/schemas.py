from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class FileInfo(BaseModel):
    filename: str
    size: int
    block_count: int
    status: str
    is_directory: bool = False


class BlockPlan(BaseModel):
    filename: str
    total_blocks: int
    block_plan: list["BlockAssignment"]


class BlockAssignment(BaseModel):
    block_id: str
    block_index: int
    primary_url: str
    secondary_url: str
    size_bytes: int


class DataNodeReport(BaseModel):
    datanode_url: str
    block_ids: list[str]


class FilePutRequest(BaseModel):
    filename: str
    file_size: int


class FileGetResponse(BaseModel):
    filename: str
    size: int
    blocks: list[dict]


class DirectoryRequest(BaseModel):
    dirname: str
