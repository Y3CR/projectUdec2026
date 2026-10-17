import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
load_dotenv()

from app import db
import app.models

src = create_engine("sqlite:///ucundinamarca.db")
dst = create_engine(URL.create(
    "mssql+pyodbc",
    host=os.environ["DB_HOST"],
    database=os.environ["DB_NAME"],
    query={"driver": "ODBC Driver 17 for SQL Server",
           "Trusted_Connection": "yes"},
))

db.metadata.create_all(dst)

with src.connect() as s, dst.begin() as d:
    for t in db.metadata.sorted_tables:
        rows = [dict(r._mapping) for r in s.execute(select(t))]
        ident = t.autoincrement_column is not None
        if rows:
            if ident:
                d.execute(text(f"SET IDENTITY_INSERT [{t.name}] ON"))
            d.execute(t.insert(), rows)
            if ident:
                d.execute(text(f"SET IDENTITY_INSERT [{t.name}] OFF"))
        print(f"{t.name}: {len(rows)} filas")