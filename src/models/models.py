from pydantic import UUID4, BaseModel, Field


class Note(BaseModel):
    user_id: int
    text: str
    space_id: UUID4
    type: str


class RequestID(BaseModel):
    request_id: UUID4


class FullMessage(Note, BaseModel):
    """
    Класс для определения полного сообщения из RabbitMQ после проведения операции
    """

    request_id: UUID4
    operation: str
    file_field: str = Field(serialization_alias="file", validation_alias="file")
    created: int | None = None
