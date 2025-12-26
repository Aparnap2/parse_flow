"""
Sarah AI Blueprint Builder Implementation

This module implements the Blueprint Builder feature for Sarah AI,
allowing users to define custom extraction schemas for their documents.
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import re

@dataclass
class FieldDefinition:
    """Represents a single field in a blueprint schema"""
    name: str
    field_type: str  # 'text', 'currency', 'number', 'date'
    instruction: str
    required: bool = True

@dataclass
class Blueprint:
    """Represents a complete extraction blueprint"""
    id: str
    user_id: str
    name: str
    fields: List[FieldDefinition]
    target_sheet_id: Optional[str] = None
    created_at: str = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the blueprint to a dictionary representation"""
        result = asdict(self)
        # Convert field objects to dictionaries
        result['fields'] = [asdict(field) for field in self.fields]
        return result
    
    def to_json(self) -> str:
        """Convert the blueprint to a JSON string"""
        return json.dumps(self.to_dict())


class BlueprintBuilder:
    """Manages the creation and storage of extraction blueprints"""
    
    def __init__(self):
        self.blueprints: Dict[str, Blueprint] = {}
        self.users_to_blueprints: Dict[str, List[str]] = {}
    
    def create_blueprint(
        self, 
        user_id: str, 
        name: str, 
        fields: List[Dict[str, str]], 
        target_sheet_id: Optional[str] = None
    ) -> Blueprint:
        """Create a new extraction blueprint"""
        # Validate field definitions
        validated_fields = []
        for field_data in fields:
            field = FieldDefinition(
                name=field_data['name'],
                field_type=field_data.get('type', 'text'),
                instruction=field_data.get('instruction', ''),
                required=field_data.get('required', True)
            )
            validated_fields.append(field)
        
        # Generate blueprint ID
        blueprint_id = f"bp_{len(self.blueprints) + 1}_{int(datetime.utcnow().timestamp())}"
        
        # Create the blueprint
        blueprint = Blueprint(
            id=blueprint_id,
            user_id=user_id,
            name=name,
            fields=validated_fields,
            target_sheet_id=target_sheet_id
        )
        
        # Store the blueprint
        self.blueprints[blueprint_id] = blueprint
        
        # Link to user
        if user_id not in self.users_to_blueprints:
            self.users_to_blueprints[user_id] = []
        self.users_to_blueprints[user_id].append(blueprint_id)
        
        return blueprint
    
    def get_blueprint(self, blueprint_id: str) -> Optional[Blueprint]:
        """Retrieve a blueprint by ID"""
        return self.blueprints.get(blueprint_id)
    
    def get_user_blueprints(self, user_id: str) -> List[Blueprint]:
        """Get all blueprints for a user"""
        blueprint_ids = self.users_to_blueprints.get(user_id, [])
        return [self.blueprints[bp_id] for bp_id in blueprint_ids if bp_id in self.blueprints]
    
    def update_blueprint(self, blueprint_id: str, **updates) -> Optional[Blueprint]:
        """Update an existing blueprint"""
        if blueprint_id not in self.blueprints:
            return None
        
        blueprint = self.blueprints[blueprint_id]
        
        # Update fields if provided
        if 'fields' in updates:
            validated_fields = []
            for field_data in updates['fields']:
                field = FieldDefinition(
                    name=field_data['name'],
                    field_type=field_data.get('type', 'text'),
                    instruction=field_data.get('instruction', ''),
                    required=field_data.get('required', True)
                )
                validated_fields.append(field)
            blueprint.fields = validated_fields
        
        # Update other fields if provided
        if 'name' in updates:
            blueprint.name = updates['name']
        if 'target_sheet_id' in updates:
            blueprint.target_sheet_id = updates['target_sheet_id']
        
        return blueprint
    
    def delete_blueprint(self, blueprint_id: str) -> bool:
        """Delete a blueprint"""
        if blueprint_id not in self.blueprints:
            return False
        
        blueprint = self.blueprints[blueprint_id]
        
        # Remove from user's list
        if blueprint.user_id in self.users_to_blueprints:
            user_bps = self.users_to_blueprints[blueprint.user_id]
            if blueprint_id in user_bps:
                user_bps.remove(blueprint_id)
        
        # Delete the blueprint
        del self.blueprints[blueprint_id]
        return True


def validate_blueprint_schema(schema: List[Dict[str, str]]) -> Dict[str, Any]:
    """Validate a blueprint schema definition"""
    errors = []
    
    if not schema:
        errors.append("Schema must contain at least one field")
        return {"valid": False, "errors": errors}
    
    field_names = set()
    for i, field in enumerate(schema):
        # Check required fields
        if "name" not in field:
            errors.append(f"Field {i}: Missing required 'name' property")
        else:
            if field["name"] in field_names:
                errors.append(f"Field {i}: Duplicate field name '{field['name']}'")
            field_names.add(field["name"])
        
        if "instruction" not in field:
            errors.append(f"Field {i}: Missing required 'instruction' property")
        
        # Validate field type if provided
        field_type = field.get("type", "text")
        if field_type not in ["text", "currency", "number", "date"]:
            errors.append(f"Field {i}: Invalid field type '{field_type}'. Must be one of: text, currency, number, date")
    
    return {"valid": len(errors) == 0, "errors": errors}


def simulate_blueprint_creation():
    """Simulate the creation of a blueprint to demonstrate functionality"""
    print("=== Blueprint Builder Simulation ===\n")
    
    builder = BlueprintBuilder()
    
    # Sample user
    user_id = "user_12345"
    
    # Sample blueprint schema
    sample_schema = [
        {"name": "Vendor", "type": "text", "instruction": "Extract the vendor or supplier name"},
        {"name": "Invoice Date", "type": "date", "instruction": "Extract the invoice date in YYYY-MM-DD format"},
        {"name": "Total Amount", "type": "currency", "instruction": "Extract the total amount including tax"},
        {"name": "Invoice Number", "type": "text", "instruction": "Extract the invoice reference number"}
    ]
    
    # Validate the schema
    validation_result = validate_blueprint_schema(sample_schema)
    print(f"Schema validation: {validation_result['valid']}")
    if not validation_result['valid']:
        print(f"Validation errors: {validation_result['errors']}")
        return
    
    # Create the blueprint
    blueprint = builder.create_blueprint(
        user_id=user_id,
        name="Xero Import Template",
        fields=sample_schema,
        target_sheet_id="sheet_67890"
    )
    
    print(f"Created blueprint: {blueprint.id}")
    print(f"Name: {blueprint.name}")
    print(f"User: {blueprint.user_id}")
    print(f"Fields: {len(blueprint.fields)}")
    
    print("\nField details:")
    for field in blueprint.fields:
        print(f"  - {field.name} ({field.field_type}): {field.instruction}")
    
    # Get user's blueprints
    user_blueprints = builder.get_user_blueprints(user_id)
    print(f"\nUser has {len(user_blueprints)} blueprint(s)")
    
    # Convert to JSON for API response
    blueprint_json = blueprint.to_json()
    print(f"\nBlueprint as JSON: {blueprint_json[:100]}...")
    
    print("\n=== Simulation Complete ===")


if __name__ == "__main__":
    simulate_blueprint_creation()