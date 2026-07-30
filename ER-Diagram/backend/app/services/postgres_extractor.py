"""Extract PostgreSQL metadata into SchemaViz's common schema model."""
import time
from collections import defaultdict

import psycopg

from app.schemas.connection import ConnectionRequest
from app.schemas.schema import Column, DatabaseSchema, ForeignKey, Index, Table


def extract_postgres_schema(request: ConnectionRequest, started: float | None = None) -> DatabaseSchema:
    started = started or time.monotonic()
    conn_args = dict(host=request.host, port=request.port, dbname=request.database,
                     user=request.username, password=request.password, connect_timeout=8)
    with psycopg.connect(**conn_args) as conn, conn.cursor() as cur:
        cur.execute("""
            SELECT c.oid, n.nspname, c.relname, c.relkind = 'v'
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE c.relkind IN ('r','p','v')
              AND n.nspname NOT IN ('pg_catalog','information_schema')
              AND n.nspname NOT LIKE 'pg_toast%'
            ORDER BY n.nspname,c.relname
        """)
        tables = [Table(object_id=r[0], schema_name=r[1], table_name=r[2], is_view=r[3], columns=[]) for r in cur.fetchall()]
        table_map = {t.object_id: t for t in tables}

        cur.execute("""
            SELECT a.attrelid,a.attname,format_type(a.atttypid,a.atttypmod),NOT a.attnotnull,
                   a.attidentity <> '', EXISTS (
                     SELECT 1 FROM pg_index i WHERE i.indrelid=a.attrelid AND i.indisprimary AND a.attnum=ANY(i.indkey)
                   )
            FROM pg_attribute a
            WHERE a.attrelid=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attrelid,a.attnum
        """, ([t.object_id for t in tables],))
        for oid, name, dtype, nullable, identity, primary in cur.fetchall():
            table_map[oid].columns.append(Column(name=name, data_type=dtype, is_nullable=nullable,
                                                  is_identity=identity, is_primary_key=primary))

        cur.execute("""
            SELECT con.conname, sn.nspname, sc.relname, tn.nspname, tc.relname,
                   array_agg(sa.attname ORDER BY k.ord), array_agg(ta.attname ORDER BY k.ord)
            FROM pg_constraint con
            JOIN pg_class sc ON sc.oid=con.conrelid JOIN pg_namespace sn ON sn.oid=sc.relnamespace
            JOIN pg_class tc ON tc.oid=con.confrelid JOIN pg_namespace tn ON tn.oid=tc.relnamespace
            JOIN LATERAL unnest(con.conkey,con.confkey) WITH ORDINALITY k(satt,tatt,ord) ON true
            JOIN pg_attribute sa ON sa.attrelid=sc.oid AND sa.attnum=k.satt
            JOIN pg_attribute ta ON ta.attrelid=tc.oid AND ta.attnum=k.tatt
            WHERE con.contype='f' AND con.conrelid=ANY(%s)
            GROUP BY con.oid,con.conname,sn.nspname,sc.relname,tn.nspname,tc.relname
        """, ([t.object_id for t in tables],))
        fks = [ForeignKey(constraint_name=r[0], source_schema=r[1], source_table=r[2],
                          target_schema=r[3], target_table=r[4], source_columns=r[5], target_columns=r[6])
               for r in cur.fetchall()]

        cur.execute("""
            SELECT i.indrelid,ci.relname,i.indisunique,
                   array_agg(a.attname ORDER BY x.ord) FILTER (WHERE a.attname IS NOT NULL)
            FROM pg_index i JOIN pg_class ci ON ci.oid=i.indexrelid
            JOIN LATERAL unnest(i.indkey) WITH ORDINALITY x(attnum,ord) ON true
            LEFT JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=x.attnum
            WHERE i.indrelid=ANY(%s) AND NOT i.indisprimary
            GROUP BY i.indrelid,ci.relname,i.indisunique
        """, ([t.object_id for t in tables],))
        for oid, name, unique, columns in cur.fetchall():
            table_map[oid].indexes.append(Index(name=name, index_type="BTREE", is_unique=unique, columns=columns or []))

    connected = {f"{fk.source_schema}.{fk.source_table}" for fk in fks} | {f"{fk.target_schema}.{fk.target_table}" for fk in fks}
    return DatabaseSchema(database_name=request.database, tables=tables, foreign_keys=fks,
                          extraction_time_seconds=round(time.monotonic()-started, 2), table_count=len(tables),
                          standalone_table_count=sum(f"{t.schema_name}.{t.table_name}" not in connected for t in tables))
