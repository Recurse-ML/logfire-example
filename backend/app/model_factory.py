import uuid
from typing import TypeVar, Generic, Type, Any, Dict, Optional, List, Union
from pydantic import create_model, EmailStr
from sqlmodel import SQLModel, Field, Relationship
from abc import ABC, abstractmethod
import copy

# Type variables for our factory system
T = TypeVar('T', bound=SQLModel)


class FieldMetadata:
    def __init__(
        self,
        field_type: Type,
        default: Any = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        unique: bool = False,
        index: bool = False,
        nullable: bool = False,
        primary_key: bool = False,
        foreign_key: Optional[str] = None,
        description: Optional[str] = None,
        validation_rules: Optional[List[str]] = None,
        business_constraints: Optional[Dict[str, Any]] = None,
        ui_hints: Optional[Dict[str, Any]] = None,
    ):
        self.field_type = field_type
        self.default = default
        self.min_length = min_length
        self.max_length = max_length
        self.unique = unique
        self.index = index
        self.nullable = nullable
        self.primary_key = primary_key
        self.foreign_key = foreign_key
        self.description = description
        self.validation_rules = validation_rules or []
        self.business_constraints = business_constraints or {}
        self.ui_hints = ui_hints or {}


class ModelSchema:
    def __init__(self, name: str, fields: Dict[str, FieldMetadata], relationships: Optional[Dict[str, Any]] = None):
        self.name = name
        self.fields = fields
        self.relationships = relationships or {}


class BaseModelFactory(Generic[T], ABC):
    
    def __init__(self, schema: ModelSchema):
        self.schema = schema
        # Cache for generated models to avoid regeneration
        self._base_model: Optional[Type[SQLModel]] = None
        self._create_model: Optional[Type[SQLModel]] = None
        self._update_model: Optional[Type[SQLModel]] = None
        self._update_me_model: Optional[Type[SQLModel]] = None
        self._table_model: Optional[Type[SQLModel]] = None
        self._public_model: Optional[Type[SQLModel]] = None
        self._list_public_model: Optional[Type[SQLModel]] = None
        
    @abstractmethod
    def get_domain_specific_validations(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_business_rules(self) -> Dict[str, Any]:
        pass
    
    def _create_field(self, field_name: str, metadata: FieldMetadata, for_model_type: str) -> Any:
        field_kwargs = {}
        field_type = metadata.field_type
        
        # Configure fields based on target model type
        if for_model_type == 'base':
            # Base models exclude password fields and ID
            if field_name in ['password', 'hashed_password', 'id']:
                return None
        elif for_model_type == 'create':
            # Create models exclude hashed_password, id, and owner_id (set by backend)
            if field_name in ['hashed_password', 'id', 'owner_id']:
                return None
            if metadata.nullable and field_name != 'id':
                field_kwargs['default'] = metadata.default
        elif for_model_type == 'update':
            # Update models make most fields optional to support partial updates
            if field_name in ['id', 'hashed_password']:
                return None
            field_type = Optional[metadata.field_type]
            field_kwargs['default'] = None
        elif for_model_type == 'update_me':
            # UpdateMe models restrict certain fields for security
            if field_name in ['password', 'is_superuser', 'hashed_password', 'id']:
                return None
            field_type = Optional[metadata.field_type]
            field_kwargs['default'] = None
        elif for_model_type == 'table':
            # Table models need database-specific configurations
            if field_name == 'id':
                field_kwargs.update({
                    'default_factory': uuid.uuid4,
                    'primary_key': True
                })
            if metadata.foreign_key:
                field_kwargs['foreign_key'] = metadata.foreign_key
                field_kwargs['nullable'] = not metadata.nullable
        elif for_model_type == 'public':
            # Public models exclude sensitive fields from API responses
            if field_name in ['hashed_password', 'password']:
                return None
        
        # Apply standard field constraints
        if metadata.min_length:
            field_kwargs['min_length'] = metadata.min_length
        if metadata.max_length:
            field_kwargs['max_length'] = metadata.max_length
        if metadata.unique:
            field_kwargs['unique'] = metadata.unique
        if metadata.index:
            field_kwargs['index'] = metadata.index
            
        # Apply domain-specific field configurations
        if field_name == 'email' and for_model_type in ['create', 'update']:
            field_kwargs['max_length'] = 255
            
        return (field_type, Field(**field_kwargs) if field_kwargs else Field())
    
    def _generate_model_fields(self, for_model_type: str) -> Dict[str, Any]:
        fields = {}
        
        for field_name, metadata in self.schema.fields.items():
            field_result = self._create_field(field_name, metadata, for_model_type)
            if field_result is not None:
                field_type, field_def = field_result
                fields[field_name] = (field_type, field_def)
                
        # Add relationships for table models
        if for_model_type == 'table':
            for rel_name, rel_config in self.schema.relationships.items():
                fields[rel_name] = (rel_config['type'], Relationship(**rel_config.get('kwargs', {})))
                
        return fields
    
    def get_base_model(self) -> Type[SQLModel]:
        if self._base_model is None:
            fields = self._generate_model_fields('base')
            self._base_model = create_model(
                f"{self.schema.name}Base",
                __base__=SQLModel,
                **fields
            )
        return self._base_model
    
    def get_create_model(self) -> Type[SQLModel]:
        if self._create_model is None:
            create_fields = self._generate_model_fields('create')
            
            self._create_model = create_model(
                f"{self.schema.name}Create",
                __base__=SQLModel,
                **create_fields
            )
        return self._create_model
    
    def get_update_model(self) -> Type[SQLModel]:
        if self._update_model is None:
            update_fields = self._generate_model_fields('update')
            
            self._update_model = create_model(
                f"{self.schema.name}Update",
                __base__=SQLModel,
                **update_fields
            )
        return self._update_model
    
    def get_update_me_model(self) -> Type[SQLModel]:
        if self._update_me_model is None:
            fields = self._generate_model_fields('update_me')
            
            self._update_me_model = create_model(
                f"{self.schema.name}UpdateMe",
                __base__=SQLModel,
                **fields
            )
        return self._update_me_model
    
    def get_table_model(self) -> Type[SQLModel]:
        if self._table_model is None:
            base_model = self.get_base_model()
            table_fields = self._generate_model_fields('table')
            
            # For table models, we need to exclude base fields but keep table-specific ones
            base_fields = set(base_model.model_fields.keys()) if hasattr(base_model, 'model_fields') else set()
            filtered_fields = {k: v for k, v in table_fields.items() 
                             if k not in base_fields or k in ['id', 'hashed_password']}
            
            self._table_model = create_model(
                f"{self.schema.name}",
                __base__=(base_model,),
                __table__=True,
                **filtered_fields
            )
        return self._table_model
    
    def get_public_model(self) -> Type[SQLModel]:
        if self._public_model is None:
            public_fields = self._generate_model_fields('public')
            
            # Ensure public models always include ID
            public_fields['id'] = (uuid.UUID, Field())
            
            self._public_model = create_model(
                f"{self.schema.name}Public",
                __base__=SQLModel,
                **public_fields
            )
        return self._public_model
    
    def get_list_public_model(self) -> Type[SQLModel]:
        if self._list_public_model is None:
            public_model = self.get_public_model()
            
            self._list_public_model = create_model(
                f"{self.schema.name}sPublic",
                __base__=SQLModel,
                data=(List[public_model], Field()),
                count=(int, Field())
            )
        return self._list_public_model
    
    def get_all_models(self) -> Dict[str, Type[SQLModel]]:
        return {
            'base': self.get_base_model(),
            'create': self.get_create_model(),
            'update': self.get_update_model(),
            'update_me': self.get_update_me_model(),
            'table': self.get_table_model(),
            'public': self.get_public_model(),
            'list_public': self.get_list_public_model(),
        }


class UserModelFactory(BaseModelFactory):
    
    def __init__(self):
        user_schema = ModelSchema(
            name="User",
            fields={
                'email': FieldMetadata(
                    field_type=EmailStr,
                    unique=True,
                    index=True,
                    max_length=255,
                    description="User's email address",
                    business_constraints={'domain_validation': True},
                    ui_hints={'input_type': 'email'}
                ),
                'is_active': FieldMetadata(
                    field_type=bool,
                    default=True,
                    description="Whether the user account is active"
                ),
                'is_superuser': FieldMetadata(
                    field_type=bool,
                    default=False,
                    description="Whether the user has admin privileges",
                    business_constraints={'admin_only_edit': True}
                ),
                'full_name': FieldMetadata(
                    field_type=Optional[str],
                    default=None,
                    max_length=255,
                    nullable=True,
                    description="User's full name"
                ),
                'password': FieldMetadata(
                    field_type=str,
                    min_length=8,
                    max_length=40,
                    description="User's password",
                    validation_rules=['complexity_check', 'not_common_password'],
                    business_constraints={'hash_before_store': True}
                ),
                'hashed_password': FieldMetadata(
                    field_type=str,
                    description="Hashed password for storage",
                    business_constraints={'never_expose': True}
                ),
                'id': FieldMetadata(
                    field_type=uuid.UUID,
                    primary_key=True
                )
            },
            relationships={
                'items': {
                    'type': List['Item'],
                    'kwargs': {'back_populates': 'owner', 'cascade_delete': True}
                }
            }
        )
        super().__init__(user_schema)
    
    def get_domain_specific_validations(self) -> Dict[str, Any]:
        return {
            'email_domain_validation': self._validate_email_domain,
            'password_complexity': self._validate_password_complexity,
            'admin_privilege_check': self._validate_admin_privileges,
        }
    
    def get_business_rules(self) -> Dict[str, Any]:
        return {
            'password_hashing': self._hash_password_before_store,
            'email_normalization': self._normalize_email,
            'superuser_restrictions': self._check_superuser_changes,
        }
    
    def _validate_email_domain(self, email: str) -> bool:
        return True
    
    def _validate_password_complexity(self, password: str) -> bool:
        return True
    
    def _validate_admin_privileges(self, user_data: dict) -> bool:
        return True
    
    def _hash_password_before_store(self, password: str) -> str:
        return password
    
    def _normalize_email(self, email: str) -> str:
        return email.lower().strip()
    
    def _check_superuser_changes(self, changes: dict) -> bool:
        return True


class ItemModelFactory(BaseModelFactory):
    
    def __init__(self):
        item_schema = ModelSchema(
            name="Item",
            fields={
                'title': FieldMetadata(
                    field_type=str,
                    min_length=1,
                    max_length=255,
                    description="Item title",
                    business_constraints={'content_filter': True},
                    ui_hints={'placeholder': 'Enter item title'}
                ),
                'description': FieldMetadata(
                    field_type=Optional[str],
                    default=None,
                    max_length=255,
                    nullable=True,
                    description="Item description",
                    business_constraints={'content_filter': True, 'markdown_allowed': True}
                ),
                'owner_id': FieldMetadata(
                    field_type=uuid.UUID,
                    foreign_key="user.id",
                    nullable=False,
                    description="ID of the item owner"
                ),
                'id': FieldMetadata(
                    field_type=uuid.UUID,
                    primary_key=True
                )
            },
            relationships={
                'owner': {
                    'type': Optional['User'],
                    'kwargs': {'back_populates': 'items'}
                }
            }
        )
        super().__init__(item_schema)
    
    def get_domain_specific_validations(self) -> Dict[str, Any]:
        return {
            'title_content_check': self._check_title_content,
            'description_markdown_validation': self._validate_markdown,
            'ownership_validation': self._validate_ownership,
        }
    
    def get_business_rules(self) -> Dict[str, Any]:
        return {
            'auto_slug_generation': self._generate_slug_from_title,
            'ownership_assignment': self._assign_owner,
            'duplicate_title_check': self._check_duplicate_titles,
        }
    
    def _check_title_content(self, title: str) -> bool:
        return True
    
    def _validate_markdown(self, description: str) -> bool:
        return True
    
    def _validate_ownership(self, item_data: dict, current_user: Any) -> bool:
        return True
    
    def _generate_slug_from_title(self, title: str) -> str:
        return title.lower().replace(' ', '-')
    
    def _assign_owner(self, item_data: dict, current_user: Any) -> dict:
        return item_data
    
    def _check_duplicate_titles(self, title: str, user_id: uuid.UUID) -> bool:
        return True


class ModelFactoryRegistry:
    
    _factories: Dict[str, BaseModelFactory] = {}
    
    @classmethod
    def register(cls, name: str, factory: BaseModelFactory):
        cls._factories[name] = factory
    
    @classmethod
    def get_factory(cls, name: str) -> BaseModelFactory:
        if name not in cls._factories:
            raise ValueError(f"No factory registered for {name}")
        return cls._factories[name]
    
    @classmethod
    def get_all_models_for(cls, entity_name: str) -> Dict[str, Type[SQLModel]]:
        factory = cls.get_factory(entity_name)
        return factory.get_all_models()


def setup_model_factories():
    # Register entity factories
    ModelFactoryRegistry.register("User", UserModelFactory())
    ModelFactoryRegistry.register("Item", ItemModelFactory())


# Initialize factories on module import
setup_model_factories() 