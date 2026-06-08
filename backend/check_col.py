import os
from sqlalchemy import create_engine, text
engine = create_engine(os.getenv('AACT_DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema='ctgov' AND table_name='studies' AND column_name LIKE '%expanded%'"))
    for row in result:
        print(row[0])
