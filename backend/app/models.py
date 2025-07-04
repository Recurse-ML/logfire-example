import uuid

from pydantic import EmailStr
from sqlmodel import Field, SQLModel

# Import our new factory system
from .model_factory import ModelFactoryRegistry, setup_model_factories

# Initialize the factory system and generate all entity models
setup_model_factories()

# Import generated models from the factory registry
user_models = ModelFactoryRegistry.get_all_models_for("User")
item_models = ModelFactoryRegistry.get_all_models_for("Item")

# Factory-generated User models
UserBase = user_models['base']
UserCreate = user_models['create']
UserUpdate = user_models['update']
UserUpdateMe = user_models['update_me']
User = user_models['table']
UserPublic = user_models['public']
UsersPublic = user_models['list_public']

# Factory-generated Item models
ItemBase = item_models['base']
ItemCreate = item_models['create']
ItemUpdate = item_models['update']
Item = item_models['table']
ItemPublic = item_models['public']
ItemsPublic = item_models['list_public']

# Non-factory models that don't fit the standard CRUD pattern
class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=40)
    full_name: str | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=40)
    new_password: str = Field(min_length=8, max_length=40)


# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=40)
