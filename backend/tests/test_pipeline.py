import unittest
import os
import sys
from sqlalchemy.orm import Session

# Add project root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.database import engine, SessionLocal, Base
from backend.app.models import IngestionJob, MockClickHouseTable
from backend.app.services.clickhouse_service import ClickHouseService
from backend.app.services.validation_service import ValidationService

class TestIngestionPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create tables in SQLite memory DB or local metadata file
        Base.metadata.create_all(bind=engine)
        cls.db = SessionLocal()
        
    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_01_emulator_table_creation(self):
        # Setup mock ClickHouse schema
        schema = [
            {"name": "id", "type": "UInt32", "nullable": False},
            {"name": "user_id", "type": "String", "nullable": False},
            {"name": "activity", "type": "String", "nullable": False},
            {"name": "timestamp", "type": "DateTime", "nullable": False}
        ]
        
        table = ClickHouseService.create_mock_table_in_emulator(
            database="default",
            table_name="test_activities",
            schema=schema,
            db_session=self.db
        )
        
        self.assertEqual(table.table_name, "test_activities")
        self.assertEqual(table.database, "default")
        self.assertEqual(len(table.schema_json), 4)

    def test_02_schema_validation_strict_mode(self):
        # Target ClickHouse schema
        ch_schema = [
            {"name": "id", "type": "UInt32", "nullable": False},
            {"name": "user_id", "type": "String", "nullable": False},
            {"name": "activity", "type": "String", "nullable": False}
        ]
        
        # Scenario A: Excel has exactly matching headers
        excel_cols_correct = [
            {"original_name": "id", "normalized_name": "id"},
            {"original_name": "user_id", "normalized_name": "user_id"},
            {"original_name": "activity", "normalized_name": "activity"}
        ]
        ok, msg, errs = ValidationService.validate_schema(excel_cols_correct, ch_schema, mode="STRICT")
        self.assertTrue(ok)
        self.assertEqual(len(errs), 0)
        
        # Scenario B: Excel lacks required 'user_id'
        excel_cols_missing = [
            {"original_name": "id", "normalized_name": "id"},
            {"original_name": "activity", "normalized_name": "activity"}
        ]
        ok, msg, errs = ValidationService.validate_schema(excel_cols_missing, ch_schema, mode="STRICT")
        self.assertFalse(ok)
        self.assertTrue(any("missing" in e["error_reason"].lower() for e in errs))

        # Scenario C: Excel has extra unexpected column in STRICT mode
        excel_cols_extra = [
            {"original_name": "id", "normalized_name": "id"},
            {"original_name": "user_id", "normalized_name": "user_id"},
            {"original_name": "activity", "normalized_name": "activity"},
            {"original_name": "extra", "normalized_name": "extra"}
        ]
        ok, msg, errs = ValidationService.validate_schema(excel_cols_extra, ch_schema, mode="STRICT")
        self.assertFalse(ok)
        self.assertTrue(any("does not exist in the clickhouse table" in e["error_reason"].lower() for e in errs))

    def test_03_row_cell_type_validation(self):
        ch_schema = [
            {"name": "id", "type": "UInt32", "nullable": False},
            {"name": "age", "type": "Int32", "nullable": True}
        ]
        
        # Valid Row
        valid_rows = [{"id": 101, "age": 25}]
        errs = ValidationService.validate_rows_chunk(valid_rows, ch_schema, start_row_num=1)
        self.assertEqual(len(errs), 0)
        
        # Invalid Row: Float instead of UInt32
        invalid_rows_1 = [{"id": "abc", "age": 25}]
        errs = ValidationService.validate_rows_chunk(invalid_rows_1, ch_schema, start_row_num=1)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["column_name"], "id")
        self.assertTrue("convert" in errs[0]["error_reason"].lower())

        # Invalid Row: Null in non-nullable field
        invalid_rows_2 = [{"id": None, "age": 25}]
        errs = ValidationService.validate_rows_chunk(invalid_rows_2, ch_schema, start_row_num=1)
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["column_name"], "id")
        self.assertTrue("non-nullable" in errs[0]["error_reason"].lower())

if __name__ == "__main__":
    unittest.main()
