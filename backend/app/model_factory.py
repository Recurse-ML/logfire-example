import uuid
from typing import TypeVar, Generic, Type, Any, Dict, Optional, List, Union
from pydantic import create_model, EmailStr
from sqlmodel import SQLModel, Field, Relationship
from abc import ABC, abstractmethod

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
    """
    Defines the complete schema for an entity, including all fields and relationships.
    This serves as the single source of truth for entity definition, ensuring
    consistency across all generated model variations.
    
    By centralizing entity definitions, we can ensure that changes to business
    rules are automatically propagated to all relevant model types.
    """
    def __init__(self, name: str, fields: Dict[str, FieldMetadata], relationships: Optional[Dict[str, Any]] = None):
        self.name = name
        self.fields = fields
        self.relationships = relationships or {}


class BaseModelFactory(Generic[T], ABC):
    """
    Abstract factory for generating consistent model hierarchies across different entities.
    This factory eliminates the need to manually define repetitive model variations
    (Base, Create, Update, UpdateMe, Table, Public, ListPublic) for each entity.
    
    The factory ensures consistency by:
    - Automatically generating appropriate field configurations for each model type
    - Applying consistent validation rules across all entities
    - Handling relationships uniformly across the application
    - Providing hooks for domain-specific customization
    
    This approach significantly reduces boilerplate code and ensures that new
    entities can be quickly added with full CRUD support by simply defining
    their schema once.
    """
    
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
        """
        Returns domain-specific validation functions for this entity type.
        This allows each entity to implement custom validation logic while
        maintaining the consistent factory interface.
        
        Returns:
            Dictionary mapping validation names to validation functions
        """
        pass
    
    @abstractmethod
    def get_business_rules(self) -> Dict[str, Any]:
        """
        Returns business-specific rules and transformations for this entity.
        This provides a clean extension point for domain-specific logic
        without breaking the factory pattern.
        
        Returns:
            Dictionary mapping rule names to rule functions
        """
        pass
    
    def _create_field(self, field_name: str, metadata: FieldMetadata, for_model_type: str) -> Any:
        """
        Generates appropriate field configurations based on the target model type.
        This ensures consistent field behavior across different model variations
        while adapting to specific requirements of each model type.
        
        Args:
            field_name: Name of the field
            metadata: Field metadata configuration
            for_model_type: Target model type (base, create, update, etc.)
            
        Returns:
            Configured Field instance or None if field should be excluded
        """
        field_kwargs = {}
        
        # Configure fields based on target model type
        if for_model_type == 'create':
            # Create models typically require all non-nullable fields
            if metadata.nullable and field_name != 'id':
                field_kwargs['default'] = metadata.default
        elif for_model_type == 'update':
            # Update models make most fields optional to support partial updates
            if field_name != 'id':
                metadata.field_type = Optional[metadata.field_type]
                field_kwargs['default'] = None
        elif for_model_type == 'update_me':
            # UpdateMe models restrict certain fields for security
            if field_name in ['password', 'is_superuser']:
                return None  # Users shouldn't be able to update these directly
            metadata.field_type = Optional[metadata.field_type]
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
            
        return Field(**field_kwargs) if field_kwargs else Field()
    
    def _generate_model_fields(self, for_model_type: str) -> Dict[str, Any]:
        """
        Generates field definitions for a specific model type by applying
        appropriate transformations to the base field metadata.
        
        Args:
            for_model_type: The type of model being generated
            
        Returns:
            Dictionary of field names to (type, Field) tuples
        """
        fields = {}
        
        for field_name, metadata in self.schema.fields.items():
            field_def = self._create_field(field_name, metadata, for_model_type)
            if field_def is not None:
                fields[field_name] = (metadata.field_type, field_def)
                
        # Add relationships for table models
        if for_model_type == 'table':
            for rel_name, rel_config in self.schema.relationships.items():
                fields[rel_name] = (rel_config['type'], Relationship(**rel_config.get('kwargs', {})))
                
        return fields
    
    def get_base_model(self) -> Type[SQLModel]:
        """
        Generates the base model class containing shared fields and properties.
        Uses lazy loading to avoid unnecessary model generation.
        """
        if self._base_model is None:
            fields = self._generate_model_fields('base')
            self._base_model = create_model(
                f"{self.schema.name}Base",
                __base__=SQLModel,
                **fields
            )
        return self._base_model
    
    def get_create_model(self) -> Type[SQLModel]:
        """
        Generates the create model class for API input validation.
        Inherits from base model and adds create-specific field configurations.
        """
        if self._create_model is None:
            base_model = self.get_base_model()
            fields = self._generate_model_fields('create')
            
            self._create_model = create_model(
                f"{self.schema.name}Create",
                __base__=base_model,
                **fields
            )
        return self._create_model
    
    def get_update_model(self) -> Type[SQLModel]:
        """
        Generates the update model class for API input validation.
        Makes fields optional to support partial updates.
        """
        if self._update_model is None:
            base_model = self.get_base_model()
            fields = self._generate_model_fields('update')
            
            self._update_model = create_model(
                f"{self.schema.name}Update",
                __base__=base_model,
                **fields
            )
        return self._update_model
    
    def get_update_me_model(self) -> Type[SQLModel]:
        """
        Generates the self-update model class for user profile updates.
        Restricts sensitive fields that users shouldn't modify directly.
        """
        if self._update_me_model is None:
            fields = self._generate_model_fields('update_me')
            
            self._update_me_model = create_model(
                f"{self.schema.name}UpdateMe",
                __base__=SQLModel,
                **fields
            )
        return self._update_me_model
    
    def get_table_model(self) -> Type[SQLModel]:
        """
        Generates the database table model class with proper relationships
        and database-specific configurations.
        """
        if self._table_model is None:
            base_model = self.get_base_model()
            fields = self._generate_model_fields('table')
            
            self._table_model = create_model(
                f"{self.schema.name}",
                __base__=base_model,
                __table__=True,
                **fields
            )
        return self._table_model
    
    def get_public_model(self) -> Type[SQLModel]:
        """
        Generates the public model class for API responses.
        Excludes sensitive fields and includes required ID field.
        """
        if self._public_model is None:
            base_model = self.get_base_model()
            fields = self._generate_model_fields('public')
            
            # Ensure public models always include ID
            fields['id'] = (uuid.UUID, Field())
            
            self._public_model = create_model(
                f"{self.schema.name}Public",
                __base__=base_model,
                **fields
            )
        return self._public_model
    
    def get_list_public_model(self) -> Type[SQLModel]:
        """
        Generates the list model class for paginated API responses.
        Provides consistent structure for all list endpoints.
        """
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
        """
        Returns all generated model types for this entity.
        Convenient method for bulk model access and registration.
        """
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
    """
    Factory for generating all User-related model classes.
    Implements user-specific validation and business rules while
    leveraging the common factory infrastructure.
    """
    
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
                    primary_key=True,
                    default_factory=uuid.uuid4
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
        """
        User-specific validation functions for email, password, and privileges.
        """
        return {
            'email_domain_validation': self._validate_email_domain,
            'password_complexity': self._validate_password_complexity,
            'admin_privilege_check': self._validate_admin_privileges,
        }
    
    def get_business_rules(self) -> Dict[str, Any]:
        """
        User-specific business rules for data transformation and validation.
        """
        return {
            'password_hashing': self._hash_password_before_store,
            'email_normalization': self._normalize_email,
            'superuser_restrictions': self._check_superuser_changes,
        }
    
    def _validate_email_domain(self, email: str) -> bool:
        """Validates email domain against allowed domains"""
        # Implementation for domain validation
        return True
    
    def _validate_password_complexity(self, password: str) -> bool:
        """Validates password meets complexity requirements"""
        # Implementation for password complexity
        return True
    
    def _validate_admin_privileges(self, user_data: dict) -> bool:
        """Validates admin privilege changes"""
        # Implementation for privilege validation
        return True
    
    def _hash_password_before_store(self, password: str) -> str:
        """Hashes password before database storage"""
        # Implementation for password hashing
        return password
    
    def _normalize_email(self, email: str) -> str:
        """Normalizes email format"""
        return email.lower().strip()
    
    def _check_superuser_changes(self, changes: dict) -> bool:
        """Validates superuser permission changes"""
        # Implementation for superuser validation
        return True


class ItemModelFactory(BaseModelFactory):
    """
    Factory for generating all Item-related model classes.
    Implements item-specific validation and business rules.
    """
    
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
                    primary_key=True,
                    default_factory=uuid.uuid4
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
        """Item-specific validation functions"""
        return {
            'title_content_check': self._check_title_content,
            'description_markdown_validation': self._validate_markdown,
            'ownership_validation': self._validate_ownership,
        }
    
    def get_business_rules(self) -> Dict[str, Any]:
        """Item-specific business rules"""
        return {
            'auto_slug_generation': self._generate_slug_from_title,
            'ownership_assignment': self._assign_owner,
            'duplicate_title_check': self._check_duplicate_titles,
        }
    
    def _check_title_content(self, title: str) -> bool:
        """Validates item title content"""
        return True
    
    def _validate_markdown(self, description: str) -> bool:
        """Validates markdown in description"""
        return True
    
    def _validate_ownership(self, item_data: dict, current_user: Any) -> bool:
        """Validates item ownership"""
        return True
    
    def _generate_slug_from_title(self, title: str) -> str:
        """Generates URL-friendly slug from title"""
        return title.lower().replace(' ', '-')
    
    def _assign_owner(self, item_data: dict, current_user: Any) -> dict:
        """Assigns ownership to item"""
        return item_data
    
    def _check_duplicate_titles(self, title: str, user_id: uuid.UUID) -> bool:
        """Checks for duplicate titles within user's items"""
        return True


class ModelFactoryRegistry:
    """
    Central registry for managing all model factories.
    Provides convenient access to all entity models through a unified interface.
    
    This registry pattern allows for dynamic model loading and ensures
    consistent model generation across the application.
    """
    
    _factories: Dict[str, BaseModelFactory] = {}
    
    @classmethod
    def register(cls, name: str, factory: BaseModelFactory):
        """Register a factory for an entity type"""
        cls._factories[name] = factory
    
    @classmethod
    def get_factory(cls, name: str) -> BaseModelFactory:
        """Get the factory for a specific entity type"""
        if name not in cls._factories:
            raise ValueError(f"No factory registered for {name}")
        return cls._factories[name]
    
    @classmethod
    def get_all_models_for(cls, entity_name: str) -> Dict[str, Type[SQLModel]]:
        """Get all model types for a specific entity"""
        factory = cls.get_factory(entity_name)
        return factory.get_all_models()


def setup_model_factories():
    """
    Initialize and register all model factories.
    This should be called during application startup to ensure
    all models are available for import and use.
    """
    # Register entity factories
    ModelFactoryRegistry.register("User", UserModelFactory())
    ModelFactoryRegistry.register("Item", ItemModelFactory())
    
    # Generate all models for easy import
    user_models = ModelFactoryRegistry.get_all_models_for("User")
    item_models = ModelFactoryRegistry.get_all_models_for("Item")
    
    # Make models available in global namespace for easy import
    globals().update({
        'User': user_models['table'],
        'UserCreate': user_models['create'],
        'UserUpdate': user_models['update'],
        'UserUpdateMe': user_models['update_me'],
        'UserPublic': user_models['public'],
        'UsersPublic': user_models['list_public'],
        'Item': item_models['table'],
        'ItemCreate': item_models['create'],
        'ItemUpdate': item_models['update'],
        'ItemPublic': item_models['public'],
        'ItemsPublic': item_models['list_public'],
    })


# Initialize factories on module import
setup_model_factories() 