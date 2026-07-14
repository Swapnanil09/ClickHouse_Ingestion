import os
import re
import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.app.models import IngestionJob, ValidationError
from backend.app.services.clickhouse_service import ClickHouseService
from backend.app.config import settings

logger = logging.getLogger("app.services.validation")

class ValidationService:
    
    @classmethod
    def validate_file(cls, file_path: str) -> Tuple[bool, str]:
        """
        Layer 1: File Validation
        """
        if not os.path.exists(file_path):
            return False, "File does not exist on disk."
            
        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return False, "File is empty."
            
        # Check size limits (e.g. 50MB)
        max_bytes = 50 * 1024 * 1024 # 50MB
        if file_size > max_bytes:
            return False, f"File size ({file_size} bytes) exceeds limit of {max_bytes} bytes."
            
        # Check extension
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in (".xlsx", ".xlsm"):
            return False, f"Unsupported file extension {ext}. Only .xlsx and .xlsm are supported."
            
        return True, "File check passed."

    @classmethod
    def validate_table_discovery(
        cls, 
        target_table: str, 
        target_database: str, 
        connection_host: str, 
        connection_port: int, 
        connection_user: str, 
        connection_pass: str, 
        connection_secure: bool,
        db_session: Session
    ) -> Tuple[bool, str, str]:
        """
        Layer 2: Table Discovery Validation
        Returns (success, message, discovered_database)
        """
        if not target_table:
            return False, "Target table name was not provided. The system requires an explicit table name.", ""
            
        # Discover databases authorized/available
        all_dbs = ClickHouseService.discover_databases(
            connection_host, connection_port, connection_user, connection_pass, connection_secure, db_session
        )
        
        # Limit to configured allowed databases if specified in config settings
        allowed_list = [d.strip() for d in settings.ALLOWED_DATABASES.split(",") if d.strip()]
        if allowed_list:
            all_dbs = [d for d in all_dbs if d in allowed_list]
            
        if not all_dbs:
            return False, "No authorized ClickHouse databases available or configured.", ""

        # If database is explicitly provided, verify it exists and matches authorization
        if target_database and target_database.upper() != "AUTO":
            if target_database not in all_dbs:
                return False, f"Database '{target_database}' is either not found or not in allowed list.", ""
                
            # Verify table exists in the explicit database
            tables = ClickHouseService.discover_tables(
                connection_host, connection_port, connection_user, connection_pass, connection_secure, target_database, db_session
            )
            if target_table not in tables:
                return False, f"Table '{target_table}' not found in database '{target_database}'.", ""
                
            return True, "Table found successfully.", target_database

        # DATABASE=AUTO mode: search databases for the table
        matching_databases = []
        for db in all_dbs:
            tables = ClickHouseService.discover_tables(
                connection_host, connection_port, connection_user, connection_pass, connection_secure, db, db_session
            )
            if target_table in tables:
                matching_databases.append(db)
                
        if len(matching_databases) == 0:
            return False, f"Table '{target_table}' could not be found in any of the authorized databases: {all_dbs}.", ""
            
        if len(matching_databases) > 1:
            return False, f"Table '{target_table}' matches multiple databases: {matching_databases}. Explicit database name is required.", ""
            
        return True, "Table discovered automatically.", matching_databases[0]

    @classmethod
    def validate_schema(
        cls, 
        excel_columns: List[Dict[str, Any]], 
        ch_schema: List[Dict[str, Any]], 
        mode: str = "STRICT"
    ) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """
        Layer 3: Schema Validation
        Compares excel normalized columns vs ClickHouse table schema.
        Returns (success, message, validation_errors_list)
        """
        errors = []
        excel_normalized_names = [col["normalized_name"] for col in excel_columns]
        
        ch_columns_dict = {col["name"].lower(): col for col in ch_schema}
        
        # Check 1: Missing Required Columns in Excel
        # A ClickHouse column is required if it is NOT nullable and does not have a default
        for ch_col in ch_schema:
            ch_col_name = ch_col["name"]
            is_nullable = ch_col.get("nullable", False)
            has_default = ch_col.get("default") is not None
            
            # Match case-insensitively
            if ch_col_name.lower() not in excel_normalized_names:
                if not is_nullable and not has_default:
                    errors.append({
                        "column_name": ch_col_name,
                        "error_reason": f"Required ClickHouse column '{ch_col_name}' is missing from the Excel sheet."
                    })

        # Check 2: Unexpected Columns in Excel (Strict Mode only)
        if mode.upper() == "STRICT":
            for exc_col in excel_columns:
                norm_name = exc_col["normalized_name"]
                orig_name = exc_col["original_name"]
                
                # Check if it matches any ClickHouse column name case-insensitively
                if norm_name.lower() not in ch_columns_dict:
                    errors.append({
                        "column_name": orig_name,
                        "error_reason": f"Excel column '{orig_name}' (normalized: '{norm_name}') does not exist in the ClickHouse table schema."
                    })
                    
        if errors:
            return False, "Schema validation failed.", errors
            
        return True, "Schema validation passed.", []

    @classmethod
    def validate_rows_chunk(
        cls, 
        rows: List[Dict[str, Any]], 
        ch_schema: List[Dict[str, Any]], 
        start_row_num: int
    ) -> List[Dict[str, Any]]:
        """
        Layer 4 & 5: Data Type & Row Validation
        Validates a list of rows against ClickHouse schema types.
        Returns a list of error dicts:
        {"row_number": int, "column_name": str, "expected_type": str, "actual_value": str, "error_reason": str}
        """
        errors = []
        ch_cols = {col["name"].lower(): col for col in ch_schema}
        
        for idx, row in enumerate(rows):
            row_num = start_row_num + idx
            
            for col_name_lower, ch_col in ch_cols.items():
                ch_type = ch_col["type"]
                is_nullable = ch_col.get("nullable", False)
                
                # Find matching column in Excel row (case-insensitive lookup)
                excel_val = None
                found = False
                for k, v in row.items():
                    if k.lower() == col_name_lower:
                        excel_val = v
                        found = True
                        break
                        
                # Nullability check
                if excel_val is None or str(excel_val).strip() == "":
                    if not is_nullable and ch_col.get("default") is None:
                        # Required cell is empty
                        errors.append({
                            "row_number": row_num,
                            "column_name": ch_col["name"],
                            "expected_type": ch_type,
                            "actual_value": "NULL/Empty",
                            "error_reason": "Value is null/empty but column is non-nullable and has no default."
                        })
                    continue
                
                # Type checking
                val_str = str(excel_val).strip()
                
                # 1. Integers (Int8, Int16, Int32, Int64, UInt8, UInt16, UInt32, UInt64)
                if "int" in ch_type.lower():
                    try:
                        # Handle float representations of ints from Excel (e.g. "1.0")
                        val_float = float(val_str)
                        if val_float.is_integer():
                            val_int = int(val_float)
                        else:
                            raise ValueError()
                            
                        # Range checks
                        if ch_type.startswith("U"):  # Unsigned integers
                            if val_int < 0:
                                raise ValueError("Unsigned type cannot be negative.")
                                
                    except ValueError as ve:
                        errors.append({
                            "row_number": row_num,
                            "column_name": ch_col["name"],
                            "expected_type": ch_type,
                            "actual_value": val_str,
                            "error_reason": f"Value cannot be converted to integer: {str(ve)}" if str(ve) else "Invalid integer format."
                        })
                
                # 2. Floats (Float32, Float64) or Decimal
                elif "float" in ch_type.lower() or "decimal" in ch_type.lower():
                    try:
                        float(val_str)
                    except ValueError:
                        errors.append({
                            "row_number": row_num,
                            "column_name": ch_col["name"],
                            "expected_type": ch_type,
                            "actual_value": val_str,
                            "error_reason": "Value cannot be converted to floating point number."
                        })
                
                # 3. Date & DateTime
                elif "date" in ch_type.lower() or "datetime" in ch_type.lower():
                    # If it's already a datetime/date object (from openpyxl parsing)
                    if hasattr(excel_val, "strftime"):
                        continue
                        
                    # Otherwise try parsing string formats
                    parsed = False
                    for fmt in (
                        "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", 
                        "%d/%m/%Y", "%m/%d/%Y", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S"
                    ):
                        try:
                            datetime.strptime(val_str, fmt)
                            parsed = True
                            break
                        except ValueError:
                            pass
                    
                    if not parsed:
                        # Try parsing as ISO format timestamp
                        try:
                            datetime.fromisoformat(val_str.replace("Z", "+00:00"))
                            parsed = True
                        except ValueError:
                            pass
                            
                    if not parsed:
                        errors.append({
                            "row_number": row_num,
                            "column_name": ch_col["name"],
                            "expected_type": ch_type,
                            "actual_value": val_str,
                            "error_reason": "Value does not match a valid date/datetime format."
                        })
                
                # 4. Boolean
                elif "bool" in ch_type.lower():
                    if val_str.lower() not in ("true", "false", "yes", "no", "0", "1", "y", "n"):
                        errors.append({
                            "row_number": row_num,
                            "column_name": ch_col["name"],
                            "expected_type": ch_type,
                            "actual_value": val_str,
                            "error_reason": "Value is not a valid boolean indicator."
                        })
                        
        return errors
