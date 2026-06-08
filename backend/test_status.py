import os
from sqlalchemy import create_engine, text
engine = create_engine(os.getenv('AACT_DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text("SELECT overall_status, COUNT(*) FROM ctgov.studies GROUP BY overall_status ORDER BY COUNT(*) DESC LIMIT 20"))
    for row in result:
        print(row[0], row[1])
