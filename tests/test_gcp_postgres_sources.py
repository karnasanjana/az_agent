"""Postgres / BigQuery / GCS sources each compile to a <source>->bronze Copy
(not a landing file) and render to the right ADF connector JSON. Mirrors
test_dataverse_source.py for the three new external sources."""

import os

from agent.builder import (
    _COPY_SOURCE_TYPE, _source_read_settings, build_dataset, build_linked_service,
)
from agent.compiler import compile_plan
from models.logical import EntityTransform, LogicalColumn, LogicalPlan, LogicalSource, OutputPlan
from models.spec import DatasetKind


def _plan(source: LogicalSource) -> LogicalPlan:
    return LogicalPlan(
        project="ext",
        sources=[source],
        transforms=[EntityTransform(entity="orders", dedup_keys=["id"])],
        outputs=[OutputPlan(name="orders_out", from_entities=["orders"])],
    )


def _bronze_copy(spec, entity="orders"):
    return next(a for pl in spec.pipelines for a in pl.activities
               if a.type == "Copy" and a.sink_dataset == f"ds_bronze_{entity}")


def test_postgres_source():
    # A REMOTE (cloud-reachable) Postgres compiles to the ADF PostgreSqlV2 Copy
    # connector. A localhost server takes the app-seeded path instead — see
    # test_postgres_local_source.
    os.environ["PG_USER"] = "reader"
    os.environ["PG_PASSWORD"] = "secret"
    spec = compile_plan(_plan(LogicalSource(
        entity="orders", format="postgres",
        server="shop.postgres.database.azure.com", database="shop",
        schema_name="public", table_name="orders",
        columns=[LogicalColumn(name="id", type="long")],
    )))

    ls = next(l for l in spec.linked_services if l.type == "PostgreSqlV2")
    src = next(d for d in spec.datasets if d.name == "ds_postgres_orders")
    assert src.kind == DatasetKind.postgres_table
    assert not any(d.name == "ds_landing_orders" for d in spec.datasets)
    assert _bronze_copy(spec).source_dataset == "ds_postgres_orders"

    ls_json = build_linked_service(ls)
    assert ls_json["type"] == "PostgreSqlV2"
    assert ls_json["typeProperties"]["server"] == "shop.postgres.database.azure.com"
    assert ls_json["typeProperties"]["port"] == 5432
    assert ls_json["typeProperties"]["username"] == "reader"
    assert ls_json["typeProperties"]["password"]["value"] == "secret"  # from env, not spec

    ds_json = build_dataset(src)
    assert ds_json["type"] == "PostgreSqlV2Table"
    assert ds_json["typeProperties"] == {"schema": "public", "table": "orders"}
    assert _COPY_SOURCE_TYPE[DatasetKind.postgres_table] == "PostgreSqlV2Source"
    assert _source_read_settings(src) is None  # query source carries no storeSettings


def test_postgres_local_source():
    """A localhost Postgres can't be reached by ADF's cloud IR, so the compiler
    emits NO linked service / source dataset / Copy — just the bronze dataset the
    app seeds itself at deploy time (app._seed_local_sources)."""
    src = LogicalSource(
        entity="orders", format="postgres",
        server="localhost", database="retaildb", schema_name="public", table_name="orders",
        columns=[LogicalColumn(name="id", type="long")],
    )
    assert src.is_local_db()
    spec = compile_plan(_plan(src))

    assert not any(l.type == "PostgreSqlV2" for l in spec.linked_services)
    assert not any(d.name == "ds_postgres_orders" for d in spec.datasets)
    assert not any(a.type == "Copy" for pl in spec.pipelines for a in pl.activities)
    # bronze dataset the silver/gold flows read still exists, at the seeded path.
    bronze = next(d for d in spec.datasets if d.name == "ds_bronze_orders")
    assert (bronze.location.container, bronze.location.folder, bronze.location.file_name) \
        == ("bronze", "orders", "orders.csv")
    assert any("local database" in a for a in spec.assumptions)


def test_postgres_remote_not_local():
    assert not LogicalSource(
        entity="orders", format="postgres", server="shop.postgres.database.azure.com",
        database="shop", table_name="orders",
    ).is_local_db()


def test_is_local_db_covers_unroutable_hosts():
    def local(server):
        return LogicalSource(entity="o", format="postgres", server=server,
                             database="d", table_name="t").is_local_db()
    # unroutable from a cloud datacenter -> app-seeded
    assert local("localhost")
    assert local("127.0.0.1")
    assert local("::1")
    assert local("DESKTOP-AB12")          # bare LAN machine name (the 'No such host' case)
    assert local("192.168.1.50")          # private IPv4
    assert local("10.0.0.5")
    assert local("172.16.3.9")
    assert local("myhost.local")          # mDNS
    assert local("host.docker.internal")
    assert local("mypg:5432")             # host:port still parsed
    # publicly reachable -> stays the ADF Copy path
    assert not local("shop.postgres.database.azure.com")
    assert not local("8.8.8.8")
    assert not local("db.example.com")


def test_bigquery_source():
    # With a service-account key wired for ADF, BigQuery compiles to the ADF
    # GoogleBigQueryV2 Copy connector. Without one it's app-seeded — see
    # test_bigquery_app_seeded_keyless.
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/x/key.json"
    spec = compile_plan(_plan(LogicalSource(
        entity="orders", format="bigquery",
        gcp_project="my-proj", bq_dataset="sales", table_name="orders",
        columns=[LogicalColumn(name="id", type="long")],
    )))

    ls = next(l for l in spec.linked_services if l.type == "GoogleBigQueryV2")
    src = next(d for d in spec.datasets if d.name == "ds_bigquery_orders")
    assert src.kind == DatasetKind.bigquery_object
    assert _bronze_copy(spec).source_dataset == "ds_bigquery_orders"

    ls_json = build_linked_service(ls)
    assert ls_json["type"] == "GoogleBigQueryV2"
    assert ls_json["typeProperties"]["projectId"] == "my-proj"
    assert ls_json["typeProperties"]["authenticationType"] == "ServiceAuthentication"

    ds_json = build_dataset(src)
    assert ds_json["type"] == "GoogleBigQueryV2Object"
    assert ds_json["typeProperties"] == {"dataset": "sales", "table": "orders"}
    assert _COPY_SOURCE_TYPE[DatasetKind.bigquery_object] == "GoogleBigQueryV2Source"
    assert _source_read_settings(src) is None


def test_gcs_source_concrete_file():
    os.environ["GCS_ACCESS_KEY_ID"] = "AKIA"
    os.environ["GCS_SECRET_ACCESS_KEY"] = "shh"
    spec = compile_plan(_plan(LogicalSource(
        entity="orders", format="gcs",
        container="my-bucket", folder="raw/orders", file_name="orders.csv",
        columns=[LogicalColumn(name="id", type="string")],
    )))

    ls = next(l for l in spec.linked_services if l.type == "GoogleCloudStorage")
    src = next(d for d in spec.datasets if d.name == "ds_gcs_orders")
    assert src.kind == DatasetKind.gcs_csv
    assert _bronze_copy(spec).source_dataset == "ds_gcs_orders"

    ls_json = build_linked_service(ls)
    assert ls_json["type"] == "GoogleCloudStorage"
    assert ls_json["typeProperties"]["accessKeyId"] == "AKIA"
    assert ls_json["typeProperties"]["secretAccessKey"]["value"] == "shh"

    ds_json = build_dataset(src)
    assert ds_json["type"] == "DelimitedText"  # renders as CSV over a GCS location
    loc = ds_json["typeProperties"]["location"]
    assert loc["type"] == "GoogleCloudStorageLocation"
    assert loc["bucketName"] == "my-bucket"
    assert loc["fileName"] == "orders.csv"
    assert _COPY_SOURCE_TYPE[DatasetKind.gcs_csv] == "DelimitedTextSource"
    # concrete file name -> no wildcard read settings.
    assert _source_read_settings(src) is None


def test_bigquery_app_seeded_keyless():
    """No GOOGLE_APPLICATION_CREDENTIALS -> ADF has no key, so the app seeds
    bronze via keyless gcloud auth. Compiler emits NO linked service / source
    dataset / Copy — just the bronze dataset the flows read (like local Postgres)."""
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    src = LogicalSource(
        entity="orders", format="bigquery", gcp_project="my-proj",
        bq_dataset="sales", table_name="orders",
        columns=[LogicalColumn(name="id", type="long")],
    )
    assert src.is_app_seeded() and not src.is_local_db()
    spec = compile_plan(_plan(src))

    assert not any(l.type == "GoogleBigQueryV2" for l in spec.linked_services)
    assert not any(d.name == "ds_bigquery_orders" for d in spec.datasets)
    assert not any(a.type == "Copy" for pl in spec.pipelines for a in pl.activities)
    bronze = next(d for d in spec.datasets if d.name == "ds_bronze_orders")
    assert (bronze.location.container, bronze.location.folder, bronze.location.file_name) \
        == ("bronze", "orders", "orders.csv")
    assert any("keyless gcloud" in a for a in spec.assumptions)


def test_gcs_app_seeded_keyless():
    os.environ.pop("GCS_ACCESS_KEY_ID", None)
    src = LogicalSource(
        entity="orders", format="gcs", container="my-bucket",
        folder="raw/orders", file_name="orders.csv",
        columns=[LogicalColumn(name="id", type="string")],
    )
    assert src.is_app_seeded()
    spec = compile_plan(_plan(src))
    assert not any(l.type == "GoogleCloudStorage" for l in spec.linked_services)
    assert not any(a.type == "Copy" for pl in spec.pipelines for a in pl.activities)
    assert any(d.name == "ds_bronze_orders" for d in spec.datasets)


def test_gcs_source_folder_only_wildcards():
    os.environ["GCS_ACCESS_KEY_ID"] = "AKIA"  # keep it on the ADF Copy path
    src = compile_plan(_plan(LogicalSource(
        entity="orders", format="gcs", container="my-bucket", folder="raw/orders",
    ))).datasets
    ds = next(d for d in src if d.name == "ds_gcs_orders")
    rs = _source_read_settings(ds)
    assert rs is not None and rs["type"] == "GoogleCloudStorageReadSettings"
    assert rs["wildcardFileName"] == "*"


if __name__ == "__main__":
    test_postgres_source()
    test_postgres_local_source()
    test_postgres_remote_not_local()
    test_is_local_db_covers_unroutable_hosts()
    test_bigquery_source()
    test_bigquery_app_seeded_keyless()
    test_gcs_app_seeded_keyless()
    test_gcs_source_concrete_file()
    test_gcs_source_folder_only_wildcards()
    print("OK — postgres / bigquery / gcs sources compile to <source>->bronze copies")
