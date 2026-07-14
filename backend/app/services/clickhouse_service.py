import json
import logging
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from backend.app.models import MockClickHouseTable
from backend.app.config import settings

# Try importing clickhouse_connect, handle gracefully if missing or fails
try:
    import clickhouse_connect
except ImportError:
    clickhouse_connect = None

logger = logging.getLogger("app.services.clickhouse")

class ClickHouseService:
    @staticmethod
    def _is_emulated(host: str) -> bool:
        return host.lower() in ("emulated", "mock", "localhost-mock", "localhost-emulator")

    @classmethod
    def test_connection(cls, host: str, port: int, username: str, password: str, secure: bool, db_session: Session) -> Tuple[bool, str]:
        if cls._is_emulated(host):
            return True, "Emulated ClickHouse connected successfully."
        
        if not clickhouse_connect:
            return False, "clickhouse-connect library is not installed."
        
        try:
            client = clickhouse_connect.get_client(
                host=host,
                port=port,
                username=username,
                password=password,
                secure=secure,
                connect_timeout=5
            )
            client.close()
            return True, "Connected successfully."
        except Exception as e:
            logger.error(f"ClickHouse connection failed: {str(e)}")
            return False, f"Connection failed: {str(e)}"

    @classmethod
    def discover_databases(cls, host: str, port: int, username: str, password: str, secure: bool, db_session: Session) -> List[str]:
        if cls._is_emulated(host):
            # Query the emulator tables to see what databases exist
            db_names = db_session.query(MockClickHouseTable.database).distinct().all()
            databases = [db[0] for db in db_names]
            # Ensure "default" is always present in emulated mode
            if "default" not in databases:
                databases.append("default")
            return databases
        
        if not clickhouse_connect:
            return ["default"]
            
        try:
            client = clickhouse_connect.get_client(
                host=host,
                port=port,
                username=username,
                password=password,
                secure=secure
            )
            result = client.query("SHOW DATABASES")
            client.close()
            return [row[0] for row in result.result_rows]
        except Exception as e:
            logger.error(f"ClickHouse discover_databases failed: {str(e)}")
            return ["default"]

    @classmethod
    def discover_tables(cls, host: str, port: int, username: str, password: str, secure: bool, database: str, db_session: Session) -> List[str]:
        if cls._is_emulated(host):
            tables = db_session.query(MockClickHouseTable.table_name).filter(MockClickHouseTable.database == database).all()
            return [t[0] for t in tables]
            
        if not clickhouse_connect:
            return []
            
        try:
            client = clickhouse_connect.get_client(
                host=host,
                port=port,
                username=username,
                password=password,
                secure=secure,
                database=database
            )
            result = client.query("SHOW TABLES")
            client.close()
            return [row[0] for row in result.result_rows]
        except Exception as e:
            logger.error(f"ClickHouse discover_tables failed: {str(e)}")
            return []

    @classmethod
    def get_table_schema(cls, host: str, port: int, username: str, password: str, secure: bool, database: str, table_name: str, db_session: Session) -> List[Dict[str, Any]]:
        """
        Returns a schema representation of a ClickHouse table:
        [{"name": "col1", "type": "String", "nullable": True, "default": None}]
        """
        if cls._is_emulated(host):
            mock_table = db_session.query(MockClickHouseTable).filter(
                MockClickHouseTable.database == database,
                MockClickHouseTable.table_name == table_name
            ).first()
            if not mock_table:
                return []
            # Schema json is stored in db
            return mock_table.schema_json
            
        if not clickhouse_connect:
            return []
            
        try:
            client = clickhouse_connect.get_client(
                host=host,
                port=port,
                username=username,
                password=password,
                secure=secure,
                database=database
            )
            # DESCRIBE TABLE returns: name, type, default_type, default_expression, comment, codec_expression, ttl_expression
            result = client.query(f"DESCRIBE TABLE {table_name}")
            client.close()
            
            schema = []
            for row in result.result_rows:
                col_name = row[0]
                col_type = row[1]
                
                # Check for Nullable(...)
                nullable = False
                base_type = col_type
                if col_type.startswith("Nullable("):
                    nullable = True
                    base_type = col_type[9:-1] # Strip Nullable( and )
                    
                schema.append({
                    "name": col_name,
                    "type": base_type,
                    "nullable": nullable,
                    "default": row[3] if row[3] else None
                })
            return schema
        except Exception as e:
            logger.error(f"ClickHouse get_table_schema failed: {str(e)}")
            return []

    @classmethod
    def insert_batch(cls, host: str, port: int, username: str, password: str, secure: bool, database: str, table_name: str, columns: List[str], data: List[List[Any]], db_session: Session) -> int:
        """
        Inserts batch of rows into ClickHouse. Returns number of inserted rows.
        """
        if not data:
            return 0
            
        if cls._is_emulated(host):
            mock_table = db_session.query(MockClickHouseTable).filter(
                MockClickHouseTable.database == database,
                MockClickHouseTable.table_name == table_name
            ).first()
            if not mock_table:
                raise Exception(f"Mock Table {database}.{table_name} not found in Emulator database.")
            
            # Save data inside data_json list
            current_data = list(mock_table.data_json or [])
            for row in data:
                # Zip columns and row values to form dict
                row_dict = dict(zip(columns, row))
                current_data.append(row_dict)
                
            mock_table.data_json = current_data
            mock_table.row_count = len(current_data)
            db_session.add(mock_table)
            db_session.commit()
            return len(data)
            
        if not clickhouse_connect:
            raise Exception("clickhouse-connect library is not installed.")
            
        try:
            client = clickhouse_connect.get_client(
                host=host,
                port=port,
                username=username,
                password=password,
                secure=secure,
                database=database
            )
            # Insert using client
            client.insert(table_name, data, column_names=columns)
            client.close()
            return len(data)
        except Exception as e:
            logger.error(f"ClickHouse insert_batch failed: {str(e)}")
            raise e
            
    @classmethod
    def create_mock_table_in_emulator(cls, database: str, table_name: str, schema: List[Dict[str, Any]], db_session: Session) -> MockClickHouseTable:
        """
        Helper method to set up tables in the SQLite-based ClickHouse Emulator
        """
        # Check if already exists
        existing = db_session.query(MockClickHouseTable).filter(
            MockClickHouseTable.database == database,
            MockClickHouseTable.table_name == table_name
        ).first()
        
        if existing:
            existing.schema_json = schema
            db_session.commit()
            return existing
            
        new_table = MockClickHouseTable(
            database=database,
            table_name=table_name,
            schema_json=schema,
            row_count=0,
            data_json=[]
        )
        db_session.add(new_table)
        db_session.commit()
        return new_table
