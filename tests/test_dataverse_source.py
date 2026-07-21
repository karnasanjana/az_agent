"""Dataverse source compiles to a Dataverse->bronze Copy (not a landing file)."""

from agent.builder import build_dataset, build_linked_service, _COPY_SOURCE_TYPE
from agent.compiler import compile_plan
from models.logical import (
    AggregationPlan, EntityTransform, LogicalColumn, LogicalPlan, LogicalSource,
    OutputPlan,
)
from models.spec import DatasetKind


def _plan():
    return LogicalPlan(
        project="crm",
        sources=[LogicalSource(
            entity="contacts", format="dataverse",
            dataverse_url="https://zcscmdemodev.crm.dynamics.com",
            entity_set="contacts",
            columns=[LogicalColumn(name="contactid", type="string"),
                     LogicalColumn(name="address1_city", type="string")],
        )],
        transforms=[EntityTransform(entity="contacts", dedup_keys=["contactid"])],
        outputs=[OutputPlan(
            name="contacts_by_city", from_entities=["contacts"],
            group_by=["address1_city"],
            aggregations=[AggregationPlan(name="contact_count", op="count", column="contactid")],
        )],
    )


def test_dataverse_compiles_to_copy_from_dataverse():
    spec = compile_plan(_plan())

    # Linked service is a Dataverse connector, not storage/http/sql.
    dv_ls = [ls for ls in spec.linked_services if ls.type == "CommonDataServiceForApps"]
    assert len(dv_ls) == 1, [ls.type for ls in spec.linked_services]
    assert dv_ls[0].url == "https://zcscmdemodev.crm.dynamics.com"

    # Source dataset reads honestly as ds_dataverse_*, kind = entity (no landing file).
    src = next(d for d in spec.datasets if d.name == "ds_dataverse_contacts")
    assert src.kind == DatasetKind.dataverse_entity
    assert src.entity_name == "contact"  # singular logical name for ADF
    assert not any(d.name == "ds_landing_contacts" for d in spec.datasets)

    # The bronze copy sources FROM the Dataverse dataset.
    copy = next(a for pl in spec.pipelines for a in pl.activities
                if a.type == "Copy" and a.sink_dataset == "ds_bronze_contacts")
    assert copy.source_dataset == "ds_dataverse_contacts"

    # ADF JSON: linked service uses AADServicePrincipal (Dataverse rejects MI).
    import os
    os.environ["SOURCE_CLIENT_ID"] = "test-client-id"
    os.environ["SOURCE_CLIENT_SECRET"] = "test-secret"
    ls_json = build_linked_service(dv_ls[0])
    assert ls_json["type"] == "CommonDataServiceForApps"
    assert ls_json["typeProperties"]["serviceUri"] == "https://zcscmdemodev.crm.dynamics.com"
    assert ls_json["typeProperties"]["authenticationType"] == "AADServicePrincipal"
    assert ls_json["typeProperties"]["servicePrincipalId"] == "test-client-id"
    assert ls_json["typeProperties"]["servicePrincipalCredential"]["value"] == "test-secret"

    ds_json = build_dataset(src)
    assert ds_json["type"] == "CommonDataServiceForAppsEntity"
    # ADF wants the SINGULAR logical name, not the plural entity-set.
    assert ds_json["typeProperties"]["entityName"] == "contact"
    assert _COPY_SOURCE_TYPE[DatasetKind.dataverse_entity] == "CommonDataServiceForAppsSource"

    # The Dataverse copy source must NOT carry blob storeSettings (that misled
    # ADF into treating it as a file store and mis-reading the auth type).
    from agent.builder import _source_read_settings
    assert _source_read_settings(src) is None


if __name__ == "__main__":
    test_dataverse_compiles_to_copy_from_dataverse()
    print("OK — Dataverse source compiles to a Dataverse->bronze copy")
