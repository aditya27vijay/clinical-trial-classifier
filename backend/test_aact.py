import os
from sqlalchemy import create_engine, text
engine = create_engine(os.getenv('AACT_DATABASE_URL'))
with engine.connect() as conn:
    result = conn.execute(text("SELECT COUNT(*) FROM ctgov.studies WHERE overall_status IN ('Terminated', 'Withdrawn', 'Suspended')"))
    print('Terminated trials:', result.fetchone()[0])
